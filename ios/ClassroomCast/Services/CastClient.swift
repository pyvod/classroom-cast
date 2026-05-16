import Foundation

// MARK: - Cast Event
enum CastEvent {
    case connected
    case disconnected
    case error(String)
    case message(String)
}

// MARK: - Cast Client
class CastClient: NSObject, URLSessionWebSocketDelegate {
    let host: String
    let port: Int

    private var ws: URLSessionWebSocketTask?
    private var session: URLSession!
    private var onEvent: ((CastEvent) -> Void)?
    private var pingTimer: Timer?
    private var reconnectTimer: Timer?
    private var isManuallyClosed = false
    private var isConnected = false

    init(host: String, port: Int) {
        // iOS app uses HTTP/WS, not HTTPS/WSS. Auto-fix 8443→8080.
        let actualPort = port == 8443 ? 8080 : port
        self.host = host
        self.port = actualPort
        super.init()
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10
        config.timeoutIntervalForResource = 300
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }

    // MARK: - WebSocket Connection
    func connectWs(onEvent: @escaping (CastEvent) -> Void) {
        self.onEvent = onEvent
        isManuallyClosed = false
        startWs()
        startPing()
    }

    private func startWs() {
        let url = URL(string: "ws://\(host):\(port)/ws")!
        ws = session.webSocketTask(with: url)
        ws?.resume()
        receiveMessage()
    }

    private func receiveMessage() {
        ws?.receive { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    if text == "PONG" {
                        // Keepalive response received
                    } else if text == "CLIENT_DISCONNECT" {
                        DispatchQueue.main.async {
                            self.onEvent?(.disconnected)
                        }
                    } else {
                        self.onEvent?(.message(text))
                    }
                case .data:
                    break
                @unknown default:
                    break
                }
                self.receiveMessage()
            case .failure(let error):
                DispatchQueue.main.async {
                    self.onEvent?(.error(error.localizedDescription))
                    self.scheduleReconnect()
                }
            }
        }
    }

    // MARK: - Keepalive (PING every 10 seconds)
    private func startPing() {
        stopPing()
        DispatchQueue.main.async {
            self.pingTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
                self?.sendText("PING")
            }
        }
    }

    private func stopPing() {
        pingTimer?.invalidate()
        pingTimer = nil
    }

    // MARK: - Auto-reconnect
    private func scheduleReconnect() {
        guard !isManuallyClosed else { return }
        stopPing()
        reconnectTimer?.invalidate()
        reconnectTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: false) { [weak self] _ in
            guard let self = self, !self.isManuallyClosed else { return }
            self.startWs()
            self.startPing()
        }
    }

    func sendFrame(_ data: Data) {
        ws?.send(.data(data)) { _ in }
    }

    func sendText(_ text: String) {
        ws?.send(.string(text)) { _ in }
    }

    func sendCastStart() { sendText("CAST_START") }
    func sendCastStop() { sendText("CAST_STOP") }

    func closeWs() {
        isManuallyClosed = true
        stopPing()
        reconnectTimer?.invalidate()
        reconnectTimer = nil
        ws?.cancel(with: .normalClosure, reason: nil)
        ws = nil
        isConnected = false
    }

    // MARK: - HTTP API
    func fetchServerInfo() async -> [String: Any]? {
        let url = URL(string: "http://\(host):\(port)/api/info")!
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            return try JSONSerialization.jsonObject(with: data) as? [String: Any]
        } catch {
            return nil
        }
    }

    func uploadPhoto(_ data: Data, filename: String) async -> Bool {
        let url = URL(string: "http://\(host):\(port)/api/upload")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"photo\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        do {
            let (respData, _) = try await URLSession.shared.data(for: request)
            if let json = try JSONSerialization.jsonObject(with: respData) as? [String: Any] {
                return json["ok"] as? Bool ?? false
            }
        } catch {}
        return false
    }

    func pushUrl(_ urlStr: String) async -> Bool {
        let url = URL(string: "http://\(host):\(port)/api/pushurl")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["url": urlStr]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                return json["ok"] as? Bool ?? false
            }
        } catch {}
        return false
    }

    // MARK: - URLSessionWebSocketDelegate
    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol: String?) {
        isConnected = true
        DispatchQueue.main.async { self.onEvent?(.connected) }
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        isConnected = false
        DispatchQueue.main.async {
            self.onEvent?(.disconnected)
            self.scheduleReconnect()
        }
    }

    deinit {
        closeWs()
    }
}

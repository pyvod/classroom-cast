import SwiftUI
import AVFoundation

struct ConnectView: View {
    var presetIp: String?
    var presetPort: String?
    var onConnected: (CastClient) -> Void
    var onScanResult: (String, String) -> Void

    @State private var ip = ""
    @State private var port = "8080"
    @State private var connecting = false
    @State private var errorMsg: String?
    @State private var showScanner = false

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                Spacer().frame(height: 40)

                // Logo
                ZStack {
                    Circle()
                        .fill(Color.blue)
                        .frame(width: 80, height: 80)
                    Text("投")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundColor(.white)
                }

                Text("班级投屏")
                    .font(.system(size: 26, weight: .bold))
                    .foregroundColor(.white)
                Text("连接班级大屏")
                    .font(.system(size: 14))
                    .foregroundColor(.gray)

                // Connection card
                VStack(alignment: .leading, spacing: 16) {
                    Text("连接服务器")
                        .font(.headline)
                        .foregroundColor(.white)

                    TextField("服务器 IP 地址", text: $ip)
                        .textFieldStyle(.plain)
                        .keyboardType(.numbersAndPunctuation)
                        .padding(12)
                        .background(Color(.systemGray6).opacity(0.2))
                        .cornerRadius(8)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.gray.opacity(0.3)))
                        .foregroundColor(.white)
                        .onChange(of: ip) { _ in errorMsg = nil }

                    TextField("端口", text: $port)
                        .textFieldStyle(.plain)
                        .keyboardType(.numberPad)
                        .padding(12)
                        .background(Color(.systemGray6).opacity(0.2))
                        .cornerRadius(8)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.gray.opacity(0.3)))
                        .foregroundColor(.white)

                    // Scan QR button
                    Button(action: { showScanner = true }) {
                        HStack {
                            Image(systemName: "qrcode.viewfinder")
                            Text("扫码识别服务器")
                        }
                        .frame(maxWidth: .infinity)
                        .padding(12)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.blue))
                    }
                    .foregroundColor(.blue)

                    // Connect button
                    Button(action: connect) {
                        Text(connecting ? "连接中..." : "连接")
                            .frame(maxWidth: .infinity)
                            .padding(14)
                            .background(Color.green)
                            .foregroundColor(.white)
                            .cornerRadius(8)
                            .font(.system(size: 16, weight: .semibold))
                    }
                    .disabled(connecting)

                    if let error = errorMsg {
                        Text(error)
                            .foregroundColor(.red)
                            .font(.system(size: 13))
                            .frame(maxWidth: .infinity)
                    }
                }
                .padding(20)
                .background(Color(.systemGray6).opacity(0.15))
                .cornerRadius(16)
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.gray.opacity(0.2)))

                // Instructions
                VStack(alignment: .leading, spacing: 8) {
                    Text("使用说明")
                        .font(.headline)
                        .foregroundColor(.white)
                    Text("1. 确保手机连接了教室 WiFi")
                    Text("2. 点击「扫码识别」扫描大屏二维码")
                    Text("3. 或手动输入大屏上的 IP 和端口号")
                    Text("4. 点击「连接」开始使用")
                }
                .font(.system(size: 13))
                .foregroundColor(.gray)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
                .background(Color(.systemGray6).opacity(0.1))
                .cornerRadius(12)

                Spacer()
            }
            .padding(24)
        }
        .background(Color(red: 0.05, green: 0.07, blue: 0.09))
        .ignoresSafeArea()
        .onAppear {
            if let ip = presetIp { self.ip = ip }
            if let port = presetPort { self.port = port }
        }
        .sheet(isPresented: $showScanner) {
            QRScannerView { code in
                showScanner = false
                if let url = URL(string: code),
                   let host = url.host {
                    self.ip = host
                    self.port = "\(url.port ?? 8080)"
                    onScanResult(host, self.port)
                }
            }
        }
    }

    private func connect() {
        guard !ip.trimmingCharacters(in: .whitespaces).isEmpty else {
            errorMsg = "请输入服务器 IP 地址"
            return
        }
        connecting = true
        errorMsg = nil

        Task {
            let portNum = Int(port) ?? 8080
            let client = CastClient(host: ip.trimmingCharacters(in: .whitespaces), port: portNum)
            let info = await client.fetchServerInfo()
            if info != nil {
                client.connectWs { event in
                    if case .connected = event {
                        DispatchQueue.main.async {
                            onConnected(client)
                        }
                    }
                }
            } else {
                DispatchQueue.main.async {
                    errorMsg = "无法连接服务器，请检查 IP 和端口"
                    connecting = false
                }
            }
        }
    }
}

// MARK: - QR Scanner
struct QRScannerView: UIViewControllerRepresentable {
    var onCode: (String) -> Void

    func makeUIViewController(context: Context) -> UIViewController {
        let vc = UIViewController()
        let capture = AVCaptureSession()

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device) else {
            return vc
        }

        capture.addInput(input)
        let output = AVCaptureMetadataOutput()
        capture.addOutput(output)

        output.setMetadataObjectsDelegate(context.coordinator, queue: .main)
        output.metadataObjectTypes = [.qr]

        let preview = AVCaptureVideoPreviewLayer(session: capture)
        preview.frame = vc.view.bounds
        preview.videoGravity = .resizeAspectFill
        vc.view.layer.addSublayer(preview)

        DispatchQueue.global().async { capture.startRunning() }

        context.coordinator.preview = preview
        return vc
    }

    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onCode: onCode) }

    class Coordinator: NSObject, AVCaptureMetadataOutputObjectsDelegate {
        var onCode: (String) -> Void
        var preview: AVCaptureVideoPreviewLayer?
        init(onCode: @escaping (String) -> Void) { self.onCode = onCode }

        func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject], from connection: AVCaptureConnection) {
            if let obj = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
               let code = obj.stringValue {
                onCode(code)
            }
        }
    }
}

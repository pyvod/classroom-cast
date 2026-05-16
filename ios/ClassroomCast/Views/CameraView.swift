import SwiftUI
import AVFoundation

struct CameraView: View {
    let client: CastClient
    @Binding var isActive: Bool
    var onStatusChange: (String) -> Void

    @State private var isStreaming = false
    @StateObject private var camera = CameraService()

    var body: some View {
        VStack(spacing: 12) {
            // Camera preview — proportional to screen width
            GeometryReader { geo in
                ZStack {
                    if camera.hasPermission {
                        CameraPreview(session: camera.session)
                            .cornerRadius(12)
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
                    } else {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(Color.black)
                        Text("需要相机权限")
                            .foregroundColor(.gray)
                    }
                }
                .frame(height: geo.size.width * 0.65)
            }
            .padding(.horizontal, 20)
            .frame(height: UIScreen.main.bounds.width * 0.65)

            VStack(spacing: 20) {
                Image(systemName: "doc.viewfinder")
                    .font(.system(size: 48))
                    .foregroundColor(.blue)
                Text("实物展台")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(.white)
                Text("将摄像头画面实时投射到大屏")
                    .font(.system(size: 13))
                    .foregroundColor(.gray)

                Button(action: {
                    if isStreaming {
                        stopStream()
                    } else {
                        startStream()
                    }
                }) {
                    Text(isStreaming ? "停止展台" : "开启展台")
                        .frame(maxWidth: .infinity)
                        .padding(14)
                        .background(isStreaming ? Color.red : Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                        .font(.system(size: 16, weight: .semibold))
                }
                .padding(.horizontal, 20)
                .disabled(!camera.hasPermission)
            }
            .padding()
        }
        .onAppear { camera.checkPermission() }
        .onDisappear { stopStream() }
    }

    private func startStream() {
        camera.startSession()
        client.sendCastStart()
        isStreaming = true
        isActive = true
        onStatusChange("实物展台已开启")

        camera.onFrame = { [self] jpegData in
            client.sendFrame(jpegData)
        }
    }

    private func stopStream() {
        camera.stopSession()
        client.sendCastStop()
        isStreaming = false
        isActive = false
        camera.onFrame = nil
        onStatusChange("展台已停止")
    }
}

// MARK: - Camera Service
class CameraService: NSObject, ObservableObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    @Published var hasPermission = false
    let session = AVCaptureSession()
    var onFrame: ((Data) -> Void)?
    private var lastFrameTime: Date = .distantPast
    private let ciContext = CIContext()  // Cache context for performance

    func checkPermission() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            hasPermission = true
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                DispatchQueue.main.async {
                    self?.hasPermission = granted
                }
            }
        default:
            hasPermission = false
        }
    }

    func startSession() {
        guard hasPermission else { return }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            self.session.beginConfiguration()
            self.session.sessionPreset = .medium

            guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
                  let input = try? AVCaptureDeviceInput(device: device) else { return }

            // Configure for 1080p if available
            if let format = device.formats.first(where: { fmt in
                let dim = CMVideoFormatDescriptionGetDimensions(fmt.formatDescription)
                return dim.width >= 1920 && dim.height >= 1080
                        && fmt.videoSupportedFrameRateRanges.contains(where: { $0.maxFrameRate >= 15 })
            }) {
                try? device.lockForConfiguration()
                device.activeFormat = format
                device.unlockForConfiguration()
            }

            self.session.addInput(input)

            let output = AVCaptureVideoDataOutput()
            output.alwaysDiscardsLateVideoFrames = true
            output.setSampleBufferDelegate(self, queue: DispatchQueue(label: "camera"))
            self.session.addOutput(output)

            // Set orientation to portrait
            if let conn = output.connection(with: .video) {
                conn.videoOrientation = .portrait
            }

            self.session.commitConfiguration()
            self.session.startRunning()
        }
    }

    func stopSession() {
        session.stopRunning()
    }

    // Sample buffer delegate — ~6 fps throttle
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        let now = Date()
        guard now.timeIntervalSince(lastFrameTime) >= 0.15 else { return }
        lastFrameTime = now

        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer),
              let onFrame = onFrame else { return }

        let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
        guard let cgImage = ciContext.createCGImage(ciImage, from: ciImage.extent) else { return }

        let jpeg = UIImage(cgImage: cgImage, scale: 1.0, orientation: .right)
            .jpegData(compressionQuality: 0.5)
        if let data = jpeg {
            onFrame(data)
        }
    }
}

// MARK: - Camera Preview (UIViewRepresentable)
struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        layer.frame = view.bounds
        view.layer.addSublayer(layer)
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        DispatchQueue.main.async {
            if let layer = uiView.layer.sublayers?.first as? AVCaptureVideoPreviewLayer {
                layer.frame = uiView.bounds
                layer.session = session
            }
        }
    }
}

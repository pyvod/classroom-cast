import SwiftUI
import ReplayKit
import UIKit

struct ScreenMirrorView: View {
    let client: CastClient
    @Binding var isActive: Bool
    var onStatusChange: (String) -> Void

    @State private var isMirroring = false

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "display")
                .font(.system(size: 48))
                .foregroundColor(.blue)
            Text("屏幕镜像")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(.white)
            Text("将手机屏幕实时投射到大屏")
                .font(.system(size: 13))
                .foregroundColor(.gray)

            Text("提示：切换到其他应用或锁屏会导致投屏中断")
                .font(.system(size: 12))
                .foregroundColor(.orange)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 20)

            Spacer().frame(height: 20)

            Button(action: {
                if isMirroring {
                    stopMirroring()
                } else {
                    startMirroring()
                }
            }) {
                Text(isMirroring ? "停止投屏" : "开始投屏")
                    .frame(maxWidth: .infinity)
                    .padding(14)
                    .background(isMirroring ? Color.red : Color.green)
                    .foregroundColor(.white)
                    .cornerRadius(8)
                    .font(.system(size: 16, weight: .semibold))
            }
            .padding(.horizontal, 20)

            // Reconnect button if disconnected
            if !isMirroring && isActive {
                Button(action: startMirroring) {
                    Text("重新连接")
                        .frame(maxWidth: .infinity)
                        .padding(14)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.blue))
                        .foregroundColor(.blue)
                        .cornerRadius(8)
                }
                .padding(.horizontal, 20)
            }

            Spacer()
        }
        .padding()
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.willResignActiveNotification)) { _ in
            // App going to background — iOS stops ReplayKit capture
            if isMirroring {
                // The capture will be stopped by iOS; update UI state
                client.sendCastStop()
                DispatchQueue.main.async {
                    isMirroring = false
                    isActive = false
                    onStatusChange("切换到其他应用，投屏已中断")
                }
            }
        }
    }

    private func startMirroring() {
        let recorder = RPScreenRecorder.shared()
        recorder.isMicrophoneEnabled = false

        recorder.startCapture { [self] sampleBuffer, type, error in
            if let error = error {
                DispatchQueue.main.async {
                    onStatusChange("镜像错误: \(error.localizedDescription)")
                }
                return
            }

            guard type == .video,
                  let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

            let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
            let context = CIContext()
            guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else { return }

            let jpegData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.3)
            if let data = jpegData {
                client.sendFrame(data)
            }
        } completionHandler: { [self] error in
            DispatchQueue.main.async {
                if let error = error {
                    onStatusChange("启动失败: \(error.localizedDescription)")
                    isMirroring = false
                    isActive = false
                } else {
                    isMirroring = true
                    isActive = true
                    client.sendCastStart()
                    onStatusChange("屏幕镜像已开始")
                }
            }
        }
    }

    private func stopMirroring() {
        RPScreenRecorder.shared().stopCapture { [self] error in
            DispatchQueue.main.async {
                isMirroring = false
                isActive = false
                client.sendCastStop()
                onStatusChange("投屏已停止")
            }
        }
    }
}

import SwiftUI

struct ControlView: View {
    let client: CastClient
    var onDisconnect: () -> Void

    @State private var selectedTab = 0
    @State private var statusText = "已连接服务器"
    @State private var isStreamActive = false
    @State private var isCameraActive = false

    var body: some View {
        VStack(spacing: 0) {
            // Top bar
            HStack {
                Text("班级投屏")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(.white)
                Spacer()
                Circle()
                    .fill(isStreamActive || isCameraActive ? Color.green : Color.gray)
                    .frame(width: 8, height: 8)
                Text(isStreamActive || isCameraActive ? "投屏中" : "已连接")
                    .font(.system(size: 13))
                    .foregroundColor(isStreamActive || isCameraActive ? .green : .gray)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color(red: 0.09, green: 0.10, blue: 0.13))

            // Tab selector
            Picker("", selection: $selectedTab) {
                Text("屏幕镜像").tag(0)
                Text("实物展台").tag(1)
                Text("拍照上传").tag(2)
                Text("推送网址").tag(3)
            }
            .pickerStyle(.segmented)
            .padding(12)

            // Status
            Text(statusText)
                .font(.system(size: 13))
                .foregroundColor(.gray)
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 16)
                .padding(.vertical, 4)

            // Content
            TabView(selection: $selectedTab) {
                ScreenMirrorView(
                    client: client,
                    isActive: $isStreamActive,
                    onStatusChange: { statusText = $0 }
                )
                .tag(0)

                CameraView(
                    client: client,
                    isActive: $isCameraActive,
                    onStatusChange: { statusText = $0 }
                )
                .tag(1)

                PhotoUploadView(
                    client: client,
                    onStatusChange: { statusText = $0 }
                )
                .tag(2)

                UrlPushView(
                    client: client,
                    onStatusChange: { statusText = $0 }
                )
                .tag(3)
            }
            .tabViewStyle(.page(indexDisplayMode: .never))

            // Disconnect
            Button(action: {
                client.sendCastStop()
                client.closeWs()
                onDisconnect()
            }) {
                Text("断开连接")
                    .frame(maxWidth: .infinity)
                    .padding(14)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.red))
            }
            .foregroundColor(.red)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
        }
        .background(Color(red: 0.05, green: 0.07, blue: 0.09))
        .ignoresSafeArea(.keyboard)
    }
}

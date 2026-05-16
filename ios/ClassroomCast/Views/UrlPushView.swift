import SwiftUI

struct UrlPushView: View {
    let client: CastClient
    var onStatusChange: (String) -> Void

    @State private var urlInput = ""

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "globe")
                .font(.system(size: 48))
                .foregroundColor(.blue)
            Text("网址推送")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(.white)
            Text("输入网址，大屏自动打开浏览器")
                .font(.system(size: 13))
                .foregroundColor(.gray)

            Spacer().frame(height: 16)

            VStack(alignment: .leading, spacing: 16) {
                TextField("输入网址", text: $urlInput)
                    .textFieldStyle(.plain)
                    .keyboardType(.URL)
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                    .padding(12)
                    .background(Color(.systemGray6).opacity(0.2))
                    .cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.gray.opacity(0.3)))
                    .foregroundColor(.white)

                Button(action: pushUrl) {
                    Text("推送到大屏")
                        .frame(maxWidth: .infinity)
                        .padding(14)
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                        .font(.system(size: 16, weight: .semibold))
                }
                .disabled(urlInput.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 20)
            Spacer()
        }
        .padding()
    }

    private func pushUrl() {
        var pushUrl = urlInput.trimmingCharacters(in: .whitespaces)
        guard !pushUrl.isEmpty else {
            onStatusChange("请输入网址")
            return
        }
        if !pushUrl.hasPrefix("http://") && !pushUrl.hasPrefix("https://") {
            pushUrl = "https://" + pushUrl
        }
        onStatusChange("推送中...")
        let finalUrl = pushUrl
        Task {
            let ok = await client.pushUrl(finalUrl)
            onStatusChange(ok ? "✅ 网址已推送到大屏" : "❌ 推送失败")
            if ok { urlInput = "" }
        }
    }
}

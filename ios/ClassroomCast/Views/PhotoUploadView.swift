import SwiftUI
import PhotosUI

struct PhotoUploadView: View {
    let client: CastClient
    var onStatusChange: (String) -> Void

    @State private var selectedItem: PhotosPickerItem?
    @State private var showCamera = false
    @State private var cameraImage: UIImage?

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "camera.fill")
                .font(.system(size: 48))
                .foregroundColor(.blue)
            Text("拍照上传")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(.white)
            Text("拍照或选择照片，发送到大屏显示")
                .font(.system(size: 13))
                .foregroundColor(.gray)

            Spacer().frame(height: 20)

            VStack(spacing: 12) {
                // Camera button
                Button(action: { showCamera = true }) {
                    HStack {
                        Image(systemName: "camera")
                        Text("拍照")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(14)
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(8)
                    .font(.system(size: 16, weight: .semibold))
                }

                // Photo picker
                PhotosPicker(selection: $selectedItem, matching: .images) {
                    HStack {
                        Image(systemName: "photo.on.rectangle")
                        Text("选择照片")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(14)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.gray))
                    .foregroundColor(.white)
                    .cornerRadius(8)
                }
            }
            .padding(.horizontal, 20)
            Spacer()
        }
        .padding()
        .onChange(of: selectedItem) { newItem in
            guard let item = newItem else { return }
            Task {
                if let data = try? await item.loadTransferable(type: Data.self) {
                    onStatusChange("上传中...")
                    let filename = "photo_\(Int(Date().timeIntervalSince1970)).jpg"
                    let ok = await client.uploadPhoto(data, filename: filename)
                    onStatusChange(ok ? "✅ 照片已发送" : "❌ 发送失败")
                }
                selectedItem = nil
            }
        }
        .sheet(isPresented: $showCamera) {
            CameraCaptureView { image in
                if let jpeg = image.jpegData(compressionQuality: 0.8) {
                    onStatusChange("上传中...")
                    Task {
                        let filename = "photo_\(Int(Date().timeIntervalSince1970)).jpg"
                        let ok = await client.uploadPhoto(jpeg, filename: filename)
                        onStatusChange(ok ? "✅ 照片已发送" : "❌ 发送失败")
                    }
                }
                showCamera = false
            }
        }
    }
}

// MARK: - Camera Capture (UIImagePickerController)
struct CameraCaptureView: UIViewControllerRepresentable {
    var onImage: (UIImage) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.allowsEditing = false
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onImage: onImage) }

    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        var onImage: (UIImage) -> Void
        init(onImage: @escaping (UIImage) -> Void) { self.onImage = onImage }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage {
                onImage(image)
            }
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            picker.dismiss(animated: true)
        }
    }
}

import cv2

for i in range(5):
    print(f"Tentando abrir dispositivo {i}...")
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        print(f"✅ Dispositivo {i} abriu corretamente!")
        ret, frame = cap.read()
        if ret:
            cv2.imshow(f"Camera {i}", frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        cap.release()
    else:
        print(f"❌ Dispositivo {i} não abriu.")

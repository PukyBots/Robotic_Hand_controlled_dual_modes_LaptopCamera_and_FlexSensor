print("Importing libraries...")
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import mujoco
print("Importing libraries...")
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import mujoco
import mujoco.viewer
import numpy as np
import time
import serial
import sys
import threading
print("Libraries imported successfully!")

# -----------------------------
# CONFIGURATION
# -----------------------------
COM_PORT = '/dev/ttyUSB0'  # Update if your Arduino uses a different port
BAUD_RATE = 9600

# -----------------------------
# SERIAL SETUP
# -----------------------------
try:
    print(f"Attempting to connect to Arduino on {COM_PORT}...")
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=0.01)
    time.sleep(2)
    print("Successfully connected to Arduino!")
except Exception as e:
    print(f"Serial error: {e}")
    ser = None

# -----------------------------
# MediaPipe Setup
# -----------------------------
print("Setting up MediaPipe...")
try:
    base_options = python.BaseOptions(model_asset_path="hand_landmarker.task")
    options = vision.HandLandmarkerOptions(base_options=base_options, num_hands=1)
    detector = vision.HandLandmarker.create_from_options(options)
except Exception as e:
    print(f"⚠️ MediaPipe error: {e}")
    sys.exit(1)

# -----------------------------
# MuJoCo Setup
# -----------------------------
print("Setting up MuJoCo...")
try:
    model = mujoco.MjModel.from_xml_path("right_hand.xml")
    data = mujoco.MjData(model)
    viewer = mujoco.viewer.launch_passive(model, data)
    prev_ctrl = np.zeros(model.nu)
except Exception as e:
    print(f"⚠️ MuJoCo error: {e}")
    viewer = None

print("Setting up Camera...")
cap = cv2.VideoCapture(0)
print("Camera initialized!")

# State Machine
current_mode = "CV"  # Start in Computer Vision mode
if ser:
    ser.write(b"MODE:CV\n")

# Smoothing
prev_vals = np.array([30, 30, 30, 30, 30], dtype=float)

def finger_angle(a, b, c):
    a = np.array([a.x, a.y])
    b = np.array([b.x, b.y])
    c = np.array([c.x, c.y])
    ba = a - b
    bc = c - b
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
    return np.arccos(np.clip(cos_angle, -1, 1))

def map_range(val, out_min, out_max):
    return int(np.clip(np.interp(val, [0, 2.0], [out_min, out_max]), out_min, out_max))

print("\nReady! Press 'm' to toggle between Camera (CV) and Glove mode.")

while cap.isOpened():
    if viewer and not viewer.is_running():
        break

    ret, frame = cap.read()
    if not ret: break

    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    cv2.putText(frame, f"MODE: {current_mode}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0) if current_mode == "CV" else (255, 100, 0), 2)

    # -----------------------------
    # GLOVE MODE
    # -----------------------------
    if current_mode == "GLOVE":
        if ser:
            # Read incoming data from the Arduino Receiver
            while ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    if line.startswith("GLOVE:"):
                        parts = line.split(":")[1].split(",")
                        if len(parts) == 5:
                            t, i, m, r, p = map(int, parts)
                            
                            # We map the 0-180 degree angles back to MuJoCo's 0-2.0 float range
                            if viewer:
                                ctrl = np.zeros(model.nu)
                                ctrl[4:8] = np.interp(t, [30, 170], [1.5, 0])
                                ctrl[8:11] = np.interp(i, [30, 170], [0, 2.0])
                                ctrl[11:14] = np.interp(m, [30, 180], [0, 2.0])
                                ctrl[14:17] = np.interp(r, [30, 180], [0, 2.0])
                                ctrl[17:20] = np.interp(p, [30, 180], [0, 2.0])
                                
                                ctrl = 0.7 * prev_ctrl + 0.3 * ctrl
                                data.ctrl[:] = ctrl
                                prev_ctrl = ctrl
                                mujoco.mj_step(model, data)
                                viewer.sync()
                except Exception as e:
                    pass

    # -----------------------------
    # CV MODE
    # -----------------------------
    elif current_mode == "CV":
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)

        if viewer:
            ctrl = np.zeros(model.nu)
        arduino_vals = np.array([30, 30, 30, 30, 30], dtype=float)

        if result.hand_landmarks:
            hand = result.hand_landmarks[0]

            # THUMB
            thumb_tip = hand[4]
            thumb_base = hand[2]
            thumb_dist = np.linalg.norm([thumb_tip.x - thumb_base.x, thumb_tip.y - thumb_base.y])
            thumb_bend_mj = np.clip(np.interp(thumb_dist, [0.08, 0.25], [1.5, 0]), 0, 1.5)
            thumb_dist_ard = np.linalg.norm([thumb_tip.x - hand[0].x, thumb_tip.y - hand[0].y])
            thumb_bend_ard = np.clip(np.interp(thumb_dist_ard, [0.15, 0.45], [0, 2.0]), 0, 2.0)

            if viewer:
                ctrl[4] = thumb_bend_mj * 0.4
                ctrl[5] = thumb_bend_mj * 0.7
                ctrl[6] = thumb_bend_mj
                ctrl[7] = thumb_bend_mj
                
            arduino_vals[0] = 200 - map_range(thumb_bend_ard * 1.4, 30, 170)

            # INDEX
            index_angle = finger_angle(hand[5], hand[6], hand[8])
            index_bend = np.clip(np.interp(index_angle, [0.3, 1.7], [2.0, 0]), 0, 2.0)
            if viewer: ctrl[8:11] = index_bend
            arduino_vals[1] = map_range(index_bend, 30, 170)

            # MIDDLE
            middle_angle = finger_angle(hand[9], hand[10], hand[12])
            middle_bend = np.clip(np.interp(middle_angle, [0.3, 1.7], [2.0, 0]), 0, 2.0)
            if viewer: ctrl[11:14] = middle_bend
            arduino_vals[2] = map_range(middle_bend, 30, 180)

            # RING
            ring_angle = finger_angle(hand[13], hand[14], hand[16])
            ring_bend = np.clip(np.interp(ring_angle, [0.3, 1.7], [2.0, 0]), 0, 2.0)
            if viewer: ctrl[14:17] = ring_bend
            arduino_vals[3] = map_range(ring_bend, 30, 180)

            # PINKY
            pinky_angle = finger_angle(hand[17], hand[18], hand[20])
            pinky_bend = np.clip(np.interp(pinky_angle, [0.3, 1.7], [2.0, 0]), 0, 2.0)
            if viewer: ctrl[17:20] = pinky_bend
            arduino_vals[4] = map_range(pinky_bend * 2.2, 30, 180)

            fist = (index_bend > 1.4 and middle_bend > 1.4 and ring_bend > 1.4 and pinky_bend > 1.4)
            if fist:
                arduino_vals = np.array([170, 180, 180, 180, 180], dtype=float)

        if viewer:
            ctrl = 0.7 * prev_ctrl + 0.3 * ctrl
            data.ctrl[:] = ctrl
            prev_ctrl = ctrl
            mujoco.mj_step(model, data)
            viewer.sync()

        if ser:
            arduino_vals = 0.7 * prev_vals + 0.3 * arduino_vals
            prev_vals = arduino_vals
            t, i, m, r, p = arduino_vals.astype(int)
            data_string = f"{t},{i},{m},{r},{p}\n"
            try:
                ser.write(data_string.encode('utf-8'))
            except Exception as e:
                pass

    cv2.imshow("Digital Twin - Dual Mode", frame)
    
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('m'):
        if current_mode == "CV":
            current_mode = "GLOVE"
            if ser: ser.write(b"MODE:GLOVE\n")
            print("Switched to GLOVE Mode")
        else:
            current_mode = "CV"
            if ser: ser.write(b"MODE:CV\n")
            print("Switched to CV Mode")
            
    time.sleep(0.05)

cap.release()
if ser:
    ser.close()
cv2.destroyAllWindows()
import numpy as np
import time
import serial
import sys
import threading
print("Libraries imported successfully!")

# -----------------------------
# CONFIGURATION
# -----------------------------
COM_PORT = 'COM7'  # Update if your Arduino uses a different port
BAUD_RATE = 9600

# -----------------------------
# SERIAL SETUP
# -----------------------------
try:
    print(f"Attempting to connect to Arduino on {COM_PORT}...")
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=0.01)
    time.sleep(2)
    print("Successfully connected to Arduino!")
except Exception as e:
    print(f"Serial error: {e}")
    ser = None

# -----------------------------
# MediaPipe Setup
# -----------------------------
print("Setting up MediaPipe...")
try:
    base_options = python.BaseOptions(model_asset_path="hand_landmarker.task")
    options = vision.HandLandmarkerOptions(base_options=base_options, num_hands=1)
    detector = vision.HandLandmarker.create_from_options(options)
except Exception as e:
    print(f"⚠️ MediaPipe error: {e}")
    sys.exit(1)

# -----------------------------
# MuJoCo Setup
# -----------------------------
print("Setting up MuJoCo...")
try:
    model = mujoco.MjModel.from_xml_path("right_hand.xml")
    data = mujoco.MjData(model)
    viewer = mujoco.viewer.launch_passive(model, data)
    prev_ctrl = np.zeros(model.nu)
except Exception as e:
    print(f"⚠️ MuJoCo error: {e}")
    viewer = None

print("Setting up Camera...")
cap = cv2.VideoCapture(0)
print("Camera initialized!")

# State Machine
current_mode = "CV"  # Start in Computer Vision mode
if ser:
    ser.write(b"MODE:CV\n")

# Smoothing
prev_vals = np.array([30, 30, 30, 30, 30], dtype=float)

def finger_angle(a, b, c):
    a = np.array([a.x, a.y])
    b = np.array([b.x, b.y])
    c = np.array([c.x, c.y])
    ba = a - b
    bc = c - b
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
    return np.arccos(np.clip(cos_angle, -1, 1))

def map_range(val, out_min, out_max):
    return int(np.clip(np.interp(val, [0, 2.0], [out_min, out_max]), out_min, out_max))

print("\nReady! Press 'm' to toggle between Camera (CV) and Glove mode.")

while cap.isOpened():
    if viewer and not viewer.is_running():
        break

    ret, frame = cap.read()
    if not ret: break

    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    cv2.putText(frame, f"MODE: {current_mode}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0) if current_mode == "CV" else (255, 100, 0), 2)

    # -----------------------------
    # GLOVE MODE
    # -----------------------------
    if current_mode == "GLOVE":
        if ser:
            # Read incoming data from the Arduino Receiver
            while ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    if line.startswith("GLOVE:"):
                        parts = line.split(":")[1].split(",")
                        if len(parts) == 5:
                            t, i, m, r, p = map(int, parts)
                            
                            # We map the 0-180 degree angles back to MuJoCo's 0-2.0 float range
                            if viewer:
                                ctrl = np.zeros(model.nu)
                                ctrl[4:8] = np.interp(t, [30, 170], [1.5, 0])
                                ctrl[8:11] = np.interp(i, [30, 170], [0, 2.0])
                                ctrl[11:14] = np.interp(m, [30, 180], [0, 2.0])
                                ctrl[14:17] = np.interp(r, [30, 180], [0, 2.0])
                                ctrl[17:20] = np.interp(p, [30, 180], [0, 2.0])
                                
                                ctrl = 0.7 * prev_ctrl + 0.3 * ctrl
                                data.ctrl[:] = ctrl
                                prev_ctrl = ctrl
                                mujoco.mj_step(model, data)
                                viewer.sync()
                except Exception as e:
                    pass

    # -----------------------------
    # CV MODE
    # -----------------------------
    elif current_mode == "CV":
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect(mp_image)

        if viewer:
            ctrl = np.zeros(model.nu)
        arduino_vals = np.array([30, 30, 30, 30, 30], dtype=float)

        if result.hand_landmarks:
            hand = result.hand_landmarks[0]

            # THUMB
            thumb_tip = hand[4]
            thumb_base = hand[2]
            thumb_dist = np.linalg.norm([thumb_tip.x - thumb_base.x, thumb_tip.y - thumb_base.y])
            thumb_bend_mj = np.clip(np.interp(thumb_dist, [0.08, 0.25], [1.5, 0]), 0, 1.5)
            thumb_dist_ard = np.linalg.norm([thumb_tip.x - hand[0].x, thumb_tip.y - hand[0].y])
            thumb_bend_ard = np.clip(np.interp(thumb_dist_ard, [0.15, 0.45], [0, 2.0]), 0, 2.0)

            if viewer:
                ctrl[4] = thumb_bend_mj * 0.4
                ctrl[5] = thumb_bend_mj * 0.7
                ctrl[6] = thumb_bend_mj
                ctrl[7] = thumb_bend_mj
                
            arduino_vals[0] = 200 - map_range(thumb_bend_ard * 1.4, 30, 170)

            # INDEX
            index_angle = finger_angle(hand[5], hand[6], hand[8])
            index_bend = np.clip(np.interp(index_angle, [0.3, 1.7], [2.0, 0]), 0, 2.0)
            if viewer: ctrl[8:11] = index_bend
            arduino_vals[1] = map_range(index_bend, 30, 170)

            # MIDDLE
            middle_angle = finger_angle(hand[9], hand[10], hand[12])
            middle_bend = np.clip(np.interp(middle_angle, [0.3, 1.7], [2.0, 0]), 0, 2.0)
            if viewer: ctrl[11:14] = middle_bend
            arduino_vals[2] = map_range(middle_bend, 30, 180)

            # RING
            ring_angle = finger_angle(hand[13], hand[14], hand[16])
            ring_bend = np.clip(np.interp(ring_angle, [0.3, 1.7], [2.0, 0]), 0, 2.0)
            if viewer: ctrl[14:17] = ring_bend
            arduino_vals[3] = map_range(ring_bend, 30, 180)

            # PINKY
            pinky_angle = finger_angle(hand[17], hand[18], hand[20])
            pinky_bend = np.clip(np.interp(pinky_angle, [0.3, 1.7], [2.0, 0]), 0, 2.0)
            if viewer: ctrl[17:20] = pinky_bend
            arduino_vals[4] = map_range(pinky_bend * 2.2, 30, 180)

            fist = (index_bend > 1.4 and middle_bend > 1.4 and ring_bend > 1.4 and pinky_bend > 1.4)
            if fist:
                arduino_vals = np.array([170, 180, 180, 180, 180], dtype=float)

        if viewer:
            ctrl = 0.7 * prev_ctrl + 0.3 * ctrl
            data.ctrl[:] = ctrl
            prev_ctrl = ctrl
            mujoco.mj_step(model, data)
            viewer.sync()

        if ser:
            arduino_vals = 0.7 * prev_vals + 0.3 * arduino_vals
            prev_vals = arduino_vals
            t, i, m, r, p = arduino_vals.astype(int)
            data_string = f"{t},{i},{m},{r},{p}\n"
            try:
                ser.write(data_string.encode('utf-8'))
            except Exception as e:
                pass

    cv2.imshow("Digital Twin - Dual Mode", frame)
    
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('m'):
        if current_mode == "CV":
            current_mode = "GLOVE"
            if ser: ser.write(b"MODE:GLOVE\n")
            print("Switched to GLOVE Mode")
        else:
            current_mode = "CV"
            if ser: ser.write(b"MODE:CV\n")
            print("Switched to CV Mode")
            
    time.sleep(0.05)

cap.release()
if ser:
    ser.close()
cv2.destroyAllWindows()

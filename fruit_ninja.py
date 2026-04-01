"""
🍉 Fruit Ninja - Điều khiển bằng cử chỉ tay
Nhấn D để bật/tắt debug (hiện webcam + skeleton tay)
Nhấn R chơi lại | Q/ESC thoát
"""

import cv2
import numpy as np
import random
import math
import time
import threading

# ─── Cấu hình ─────────────────────────────────────────────────────────────────
WINDOW_W, WINDOW_H  = 900, 600
MAX_LIVES           = 3
SLICE_TRAIL_LEN     = 20
PARTICLE_COUNT      = 14
GRAVITY             = 0.35
FRUIT_SPAWN_RATE    = 90
BOMB_CHANCE         = 0.15

GOLD  = (0,   200, 255)
WHITE = (255, 255, 255)
GRAY  = (120, 120, 120)
CYAN  = (255, 220, 0  )

FRUITS = [
    {"color": (50,  170, 50 ), "inner": (80,  80,  220), "r": 38},
    {"color": (30,  140, 255), "inner": (60,  200, 255), "r": 30},
    {"color": (50,  50,  220), "inner": (150, 150, 255), "r": 30},
    {"color": (0,   220, 220), "inner": (100, 255, 255), "r": 26},
    {"color": (200, 80,  180), "inner": (230, 160, 210), "r": 22},
    {"color": (60,  80,  230), "inner": (130, 140, 255), "r": 26},
]

# ─── Particle ─────────────────────────────────────────────────────────────────
class Particle:
    def __init__(self, x, y, color):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2, 7)
        self.x  = x + random.randint(-8, 8)
        self.y  = y + random.randint(-8, 8)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - 2
        self.color    = color
        self.life     = random.randint(18, 32)
        self.max_life = self.life
        self.r        = random.randint(3, 7)

    def update(self):
        self.x  += self.vx
        self.y  += self.vy
        self.vy += GRAVITY * 0.8
        self.life -= 1

    def draw(self, frame):
        if self.life <= 0:
            return
        alpha = self.life / self.max_life
        r     = max(1, int(self.r * alpha))
        color = tuple(int(c * alpha) for c in self.color)
        cv2.circle(frame, (int(self.x), int(self.y)), r, color, -1)


# ─── Trái cây / Bom ───────────────────────────────────────────────────────────
class FruitObj:
    def __init__(self, is_bomb=False):
        self.x         = random.randint(80, WINDOW_W - 80)
        self.y         = WINDOW_H + 40
        self.vx        = random.uniform(-2.5, 2.5)
        self.vy        = random.uniform(-14, -10)
        self.rot       = 0
        self.rot_speed = random.uniform(-4, 4)
        self.sliced    = False
        self.missed    = False
        self.is_bomb   = is_bomb
        self.score     = 10

        if is_bomb:
            self.r     = 30
            self.color = (40, 40, 40)
            self.inner = (80, 80, 80)
        else:
            f          = random.choice(FRUITS)
            self.r     = f["r"]
            self.color = f["color"]
            self.inner = f["inner"]

    def update(self):
        self.x   += self.vx
        self.y   += self.vy
        self.vy  += GRAVITY
        self.rot += self.rot_speed
        if self.y > WINDOW_H + 60 and not self.sliced:
            self.missed = True

    def draw(self, frame):
        if self.sliced:
            return
        cx, cy = int(self.x), int(self.y)
        if self.is_bomb:
            cv2.circle(frame, (cx, cy), self.r, (40, 40, 40), -1)
            cv2.circle(frame, (cx, cy), self.r, (80, 80, 80), 2)
            cv2.line(frame, (cx, cy - self.r),
                     (cx + 8, cy - self.r - 14), (80, 160, 255), 3)
            for _ in range(4):
                sx = cx + 8 + random.randint(-3, 3)
                sy = cy - self.r - 14 + random.randint(-4, 4)
                cv2.circle(frame, (sx, sy), random.randint(2, 5),
                           (0, random.randint(150, 255), 255), -1)
            cv2.putText(frame, "BOMB", (cx - 22, cy + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        else:
            pts_o = self._circle_pts(cx, cy, self.r, 12, self.rot)
            cv2.fillPoly(frame, [pts_o], self.color)
            pts_i = self._circle_pts(cx, cy, self.r // 2, 10, self.rot + 20)
            cv2.fillPoly(frame, [pts_i], self.inner)
            cv2.polylines(frame, [pts_o], True, WHITE, 1)

    @staticmethod
    def _circle_pts(cx, cy, r, n, offset):
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n + math.radians(offset)
            pts.append([int(cx + r * math.cos(a)), int(cy + r * math.sin(a))])
        return np.array(pts, dtype=np.int32)


# ─── Vệt chém ─────────────────────────────────────────────────────────────────
class SliceTrail:
    def __init__(self):
        self.points = []

    def add(self, pt):
        self.points.append({"pos": pt, "life": SLICE_TRAIL_LEN})

    def update(self):
        for p in self.points:
            p["life"] -= 1
        self.points = [p for p in self.points if p["life"] > 0]

    def draw(self, frame):
        alive = [p for p in self.points if p["life"] > 0]
        for i in range(1, len(alive)):
            alpha = alive[i]["life"] / SLICE_TRAIL_LEN
            t     = max(1, int(8 * alpha))
            color = (int(80 * alpha), int(220 * alpha), int(255 * alpha))
            cv2.line(frame,
                     tuple(map(int, alive[i-1]["pos"])),
                     tuple(map(int, alive[i]["pos"])),
                     color, t, cv2.LINE_AA)


# ─── Hand Tracker ─────────────────────────────────────────────────────────────
class HandTracker:
    """
    Tự động thử API cũ rồi API mới của MediaPipe.
    get_index_tip() trả về (x, y) trong không gian WINDOW_W x WINDOW_H,
    đã căn chỉnh với frame game (đã flip).
    """
    # Tất cả 21 kết nối để vẽ skeleton
    HAND_CONNECTIONS = [
        (0,1),(1,2),(2,3),(3,4),
        (0,5),(5,6),(6,7),(7,8),
        (0,9),(9,10),(10,11),(11,12),
        (0,13),(13,14),(14,15),(15,16),
        (0,17),(17,18),(18,19),(19,20),
        (5,9),(9,13),(13,17),
    ]

    def __init__(self):
        self._detector  = None
        self._mode      = None
        self._landmarks = []
        # Thread-safe detection
        self._lock      = threading.Lock()
        self._result_pt = None
        self._result_lm = []
        self._latest_frame = None
        self._thread    = None
        self._running   = False
        self._setup()
        self._start_thread()

    def _setup(self):
        import mediapipe as mp

        # Thử API cũ
        try:
            sol = mp.solutions.hands
            self._detector = sol.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )
            self._mode = "legacy"
            print("[HandTracker] ✓ mp.solutions.hands (API cũ)")
            return
        except AttributeError:
            pass

        # Thử Tasks API mới
        try:
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.vision import (
                HandLandmarkerOptions, RunningMode)
            import mediapipe.tasks as mp_tasks

            opts = HandLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(
                    model_asset_path=self._download_model()),
                running_mode=RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )
            self._detector = vision.HandLandmarker.create_from_options(opts)
            self._mode = "tasks"
            self._ts   = 0
            print("[HandTracker] ✓ mediapipe.tasks (API mới)")
            return
        except Exception as e:
            print(f"[HandTracker] Tasks API lỗi: {e}")

        raise RuntimeError("Không khởi tạo được MediaPipe!")

    @staticmethod
    def _download_model():
        import urllib.request, os
        path = "hand_landmarker.task"
        if not os.path.exists(path):
            url = ("https://storage.googleapis.com/mediapipe-models/"
                   "hand_landmarker/hand_landmarker/float16/1/"
                   "hand_landmarker.task")
            print("[HandTracker] Đang tải model (~9 MB)...")
            urllib.request.urlretrieve(url, path)
            print("[HandTracker] Tải xong!")
        return path

    def _start_thread(self):
        """Chạy detection trên thread riêng để không block game loop."""
        self._running = True
        self._ts_thread = 0
        self._thread = threading.Thread(target=self._detect_loop, daemon=True)
        self._thread.start()

    def _detect_loop(self):
        while self._running:
            frame = None
            with self._lock:
                if self._latest_frame is not None:
                    frame = self._latest_frame.copy()
                    self._latest_frame = None

            if frame is None:
                time.sleep(0.005)
                continue

            # Detect trên ảnh nhỏ 320x240 → nhanh gấp 4x
            DETECT_W, DETECT_H = 320, 240
            small = cv2.resize(frame, (DETECT_W, DETECT_H))
            sx = WINDOW_W / DETECT_W
            sy = WINDOW_H / DETECT_H

            pt  = None
            lms = []

            if self._mode == "legacy":
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                result = self._detector.process(rgb)
                if result.multi_hand_landmarks:
                    raw = result.multi_hand_landmarks[0].landmark
                    lms = [(int(lm.x * DETECT_W * sx),
                            int(lm.y * DETECT_H * sy)) for lm in raw]
                    pt  = lms[8]

            elif self._mode == "tasks":
                import mediapipe as mp
                # Unflip → detect → flip x lại
                unflipped = cv2.flip(small, 1)
                rgb = cv2.cvtColor(unflipped, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                self._ts_thread += 33
                result = self._detector.detect_for_video(
                    mp_img, self._ts_thread)
                if result.hand_landmarks:
                    raw = result.hand_landmarks[0]
                    lms = [(int((1 - lm.x) * DETECT_W * sx),
                            int(lm.y * DETECT_H * sy)) for lm in raw]
                    pt  = lms[8]

            with self._lock:
                self._result_pt = pt
                self._result_lm = lms

    def process(self, cam_bgr_flipped):
        """
        Gửi frame mới cho detection thread.
        Trả về kết quả từ lần detect trước (non-blocking).
        """
        with self._lock:
            self._latest_frame = cam_bgr_flipped
            self._landmarks    = list(self._result_lm)
            return self._result_pt

    def draw_skeleton(self, frame):
        """Vẽ skeleton tay lên frame (dùng cho debug)."""
        if not self._landmarks:
            return
        for a, b in self.HAND_CONNECTIONS:
            if a < len(self._landmarks) and b < len(self._landmarks):
                cv2.line(frame, self._landmarks[a], self._landmarks[b],
                         (0, 200, 100), 2)
        for i, pt in enumerate(self._landmarks):
            color = (0, 0, 255) if i == 8 else (255, 255, 255)
            cv2.circle(frame, pt, 5, color, -1)

    def close(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        try:
            self._detector.close()
        except Exception:
            pass


# ─── Game ─────────────────────────────────────────────────────────────────────
class FruitNinja:
    def __init__(self):
        self.tracker   = HandTracker()
        self.cap       = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 60)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # giảm buffer → ít delay
        self.debug     = False   # nhấn D để bật
        self.reset()

    def reset(self):
        self.score          = 0
        self.lives          = MAX_LIVES
        self.fruits         = []
        self.particles      = []
        self.trail          = SliceTrail()
        self.frame_cnt      = 0
        self.game_over      = False
        self.finger_pt      = None
        self.prev_pt        = None
        self.spawn_interval = FRUIT_SPAWN_RATE
        self.flash          = 0
        self.score_popups   = []

    # ── Chém ──────────────────────────────────────────────────────────────────
    def check_slice(self):
        if self.finger_pt is None or self.prev_pt is None:
            return
        fx, fy = self.finger_pt
        px, py = self.prev_pt
        # Ngưỡng chuyển động thấp hơn → nhạy hơn
        if math.hypot(fx - px, fy - py) < 5:
            return
        for fruit in self.fruits:
            if fruit.sliced or fruit.missed:
                continue
            d = self._seg_dist(fruit.x, fruit.y, px, py, fx, fy)
            if d < fruit.r + 15:   # vùng chém rộng hơn
                fruit.sliced = True
                if fruit.is_bomb:
                    self.lives -= 1
                    self.flash  = 20
                    self._spawn_particles(fruit.x, fruit.y, (60, 60, 255), 20)
                    if self.lives <= 0:
                        self.game_over = True
                else:
                    self.score += fruit.score
                    self.spawn_interval = max(
                        40, FRUIT_SPAWN_RATE - self.score // 50 * 5)
                    self._spawn_particles(fruit.x, fruit.y, fruit.color)
                    self.score_popups.append(
                        [fruit.x, fruit.y - fruit.r - 10, "+10", 40])

    @staticmethod
    def _seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)))
        return math.hypot(px - (ax + t*dx), py - (ay + t*dy))

    def _spawn_particles(self, x, y, color, n=PARTICLE_COUNT):
        for _ in range(n):
            self.particles.append(Particle(x, y, color))

    # ── HUD ───────────────────────────────────────────────────────────────────
    def draw_hud(self, frame):
        cv2.rectangle(frame, (0, 0), (WINDOW_W, 55), (20, 20, 30), -1)
        cv2.putText(frame, f"SCORE: {self.score}",
                    (20, 38), cv2.FONT_HERSHEY_DUPLEX, 1.1, GOLD, 2)
        for i in range(MAX_LIVES):
            color = (50, 50, 220) if i < self.lives else (60, 60, 60)
            self._heart(frame, WINDOW_W - 45 - i * 45, 28, 18, color)

        if self.debug:
            cv2.putText(frame, "DEBUG ON (D to toggle)",
                        (WINDOW_W//2 - 120, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 180), 1)

        if self.flash > 0:
            ov = frame.copy()
            cv2.rectangle(ov, (0, 0), (WINDOW_W, WINDOW_H), (0, 0, 200), -1)
            alpha = self.flash / 20 * 0.35
            cv2.addWeighted(ov, alpha, frame, 1 - alpha, 0, frame)
            self.flash -= 1

        new_p = []
        for p in self.score_popups:
            x, y, txt, life = p
            a = min(1.0, life / 20)
            cv2.putText(frame, txt, (int(x)-15, int(y)),
                        cv2.FONT_HERSHEY_DUPLEX, 0.9,
                        tuple(int(c * a) for c in GOLD), 2)
            p[1] -= 1.5; p[3] -= 1
            if p[3] > 0:
                new_p.append(p)
        self.score_popups = new_p

    @staticmethod
    def _heart(frame, cx, cy, size, color):
        pts = []
        for deg in range(0, 360, 6):
            t = math.radians(deg)
            x = size * (16*math.sin(t)**3) / 16
            y = -size * (13*math.cos(t) - 5*math.cos(2*t)
                         - 2*math.cos(3*t) - math.cos(4*t)) / 16
            pts.append([int(cx + x), int(cy + y)])
        cv2.fillPoly(frame, [np.array(pts, dtype=np.int32)], color)

    def draw_game_over(self, frame):
        ov = frame.copy()
        cv2.rectangle(ov, (0, 0), (WINDOW_W, WINDOW_H), (0, 0, 0), -1)
        cv2.addWeighted(ov, 0.7, frame, 0.3, 0, frame)
        cv2.putText(frame, "GAME OVER",
                    (WINDOW_W//2 - 180, WINDOW_H//2 - 50),
                    cv2.FONT_HERSHEY_DUPLEX, 2.2, (50, 50, 255), 4)
        cv2.putText(frame, f"Score: {self.score}",
                    (WINDOW_W//2 - 100, WINDOW_H//2 + 20),
                    cv2.FONT_HERSHEY_DUPLEX, 1.4, GOLD, 3)
        cv2.putText(frame, "Press R to Restart  |  Q to Quit",
                    (WINDOW_W//2 - 230, WINDOW_H//2 + 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, WHITE, 2)

    # ── Debug: hiện webcam + skeleton ─────────────────────────────────────────
    def draw_debug_overlay(self, frame, cam):
        """Ghép webcam nhỏ góc dưới-trái + vẽ skeleton."""
        self.tracker.draw_skeleton(frame)

        # Webcam nhỏ góc dưới trái
        mini_w, mini_h = 220, 165
        mini = cv2.resize(cam, (mini_w, mini_h))
        self.tracker.draw_skeleton(mini)   # cũng vẽ lên mini
        x0, y0 = 10, WINDOW_H - mini_h - 10
        frame[y0:y0+mini_h, x0:x0+mini_w] = mini
        cv2.rectangle(frame, (x0, y0), (x0+mini_w, y0+mini_h),
                      (0, 200, 100), 2)
        cv2.putText(frame, "CAM", (x0 + 5, y0 + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 180), 1)

    # ── Vòng lặp ──────────────────────────────────────────────────────────────
    def run(self):
        cv2.namedWindow("Fruit Ninja", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Fruit Ninja", WINDOW_W, WINDOW_H)

        print("\nPhím tắt:")
        print("  D  – Bật/tắt debug (hiện webcam + skeleton tay)")
        print("  R  – Chơi lại")
        print("  Q/ESC – Thoát\n")

        prev_time = time.time()

        while True:
            ret, cam_raw = self.cap.read()
            if not ret:
                break

            # Flip + resize camera về đúng kích thước game
            cam = cv2.resize(cv2.flip(cam_raw, 1), (WINDOW_W, WINDOW_H))

            # Nhận diện tay từ frame camera (cùng kích thước game)
            self.finger_pt = self.tracker.process(cam)

            # Nền tối
            frame = np.full((WINDOW_H, WINDOW_W, 3), (15, 10, 25),
                            dtype=np.uint8)

            if not self.game_over:
                self.frame_cnt += 1

                if self.frame_cnt % self.spawn_interval == 0:
                    self.fruits.append(
                        FruitObj(random.random() < BOMB_CHANCE))
                    if random.random() < 0.3:
                        self.fruits.append(FruitObj(False))

                self.check_slice()

                if self.finger_pt:
                    self.trail.add(self.finger_pt)
                self.trail.update()

                for fruit in self.fruits:
                    fruit.update()

                for fruit in self.fruits:
                    if fruit.missed and not fruit.is_bomb:
                        fruit.missed = False
                        fruit.sliced = True
                        self.lives  -= 1
                        self.flash   = 15
                        if self.lives <= 0:
                            self.game_over = True

                self.fruits = [f for f in self.fruits
                               if not f.sliced and f.y < WINDOW_H + 80]

                for p in self.particles:
                    p.update()
                self.particles = [p for p in self.particles if p.life > 0]

                self.prev_pt = self.finger_pt

            # Vẽ
            for p in self.particles:
                p.draw(frame)
            self.trail.draw(frame)
            for fruit in self.fruits:
                fruit.draw(frame)

            # Con trỏ ngón tay
            if self.finger_pt:
                fx, fy = self.finger_pt
                cv2.circle(frame, (fx, fy), 18, (0, 230, 255), 3)
                cv2.circle(frame, (fx, fy),  6, (0, 230, 255), -1)
                # Vệt sáng nhỏ tại tâm
                cv2.circle(frame, (fx, fy),  2, WHITE, -1)

            # Debug overlay
            if self.debug:
                self.draw_debug_overlay(frame, cam)

            self.draw_hud(frame)

            # Hint
            if self.frame_cnt < 180:
                a = min(1.0, (180 - self.frame_cnt) / 60)
                col = tuple(int(c * a) for c in WHITE)
                cv2.putText(frame,
                            "Giơ ngón trỏ lên và vung qua trái cây!  [D] debug",
                            (WINDOW_W//2 - 310, WINDOW_H - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, col, 2)

            # FPS
            now = time.time()
            fps = 1 / max(0.001, now - prev_time)
            prev_time = now
            cv2.putText(frame, f"FPS:{int(fps)}",
                        (WINDOW_W - 100, WINDOW_H - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, GRAY, 1)

            if self.game_over:
                self.draw_game_over(frame)

            cv2.imshow("Fruit Ninja", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
            if key == ord('r'):
                self.reset()
            if key == ord('d'):
                self.debug = not self.debug
                print(f"[Debug] {'BẬT' if self.debug else 'TẮT'}")

        self.tracker.close()
        self.cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    print("=" * 55)
    print("🍉  FRUIT NINJA - Gesture Control")
    print("=" * 55)
    game = FruitNinja()
    game.run()
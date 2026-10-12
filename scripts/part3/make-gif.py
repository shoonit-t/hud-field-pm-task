"""Part 3: draw the event-loop animation as a GIF.

    python scripts/part3/make-gif.py notes/part3/event-loop.gif

Shows why a query span reads 300 ms when the database took 10 ms. The app has one
thread and a queue. While request A's query is at the database, the thread takes a
small request (B), finishes it, then takes a heavy one (C). The answer for A comes
back while C is running, so it waits in the queue until the thread is free.
Needs Pillow. The numbers are the assignment's example, not a measurement.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, S = 1000, 580, 2  # drawn at 2x and scaled down, so text edges are smooth
FONTS = Path("C:/Windows/Fonts")

INK, MUTED, LINE, PANEL, WHITE = "#1F2328", "#667085", "#D0D7DE", "#F6F8FA", "#FFFFFF"
BLUE, BLUE_SOFT = "#2F6FEB", "#DCE8FD"  # request A, its answer and its query span
PURPLE, PURPLE_SOFT = "#7A4FC4", "#E9E0F8"  # request B, the small one
ORANGE, ORANGE_SOFT = "#C2570C", "#FBE4D0"  # request C, the heavy one
GREEN, GREEN_SOFT = "#1A7F5A", "#D7F0E5"  # the database
WAIT = "#B8C4D6"

# The story, in milliseconds
A_SENT, B_START, B_END, C_START, DB_DONE, SPAN_END = 1, 1, 4, 5, 10, 300


def font(size, bold=False):
    return ImageFont.truetype(str(FONTS / ("segoeuib.ttf" if bold else "segoeui.ttf")), size * S)


F_TITLE, F_CAPTION, F_HEAD, F_BODY, F_SMALL, F_CHIP, F_CLOCK = (
    font(23, True), font(16), font(14, True), font(14), font(12), font(13, True), font(26, True))


class Canvas:
    def __init__(self):
        self.image = Image.new("RGB", (W * S, H * S), WHITE)
        self.draw = ImageDraw.Draw(self.image)

    def box(self, x0, y0, x1, y1, fill=None, outline=None, radius=8, width=1):
        self.draw.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius * S, fill=fill, outline=outline, width=width * S)

    def rect(self, x0, y0, x1, y1, fill):
        if x1 > x0:
            self.draw.rectangle([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)

    def line(self, x0, y0, x1, y1, fill, width=1):
        self.draw.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill, width=width * S)

    def arrow(self, x0, y0, x1, y1, fill, width=2, head=7):
        """A straight horizontal arrow from (x0, y0) to (x1, y1), with its head at the end."""
        direction = 1 if x1 > x0 else -1
        self.line(x0, y0, x1 - direction * head, y1, fill, width)
        self.draw.polygon([(x1 * S, y1 * S), ((x1 - direction * head * 1.5) * S, (y1 - head) * S),
                           ((x1 - direction * head * 1.5) * S, (y1 + head) * S)], fill=fill)

    def text(self, x, y, value, fnt, fill=INK, anchor="la"):
        self.draw.text((x * S, y * S), value, font=fnt, fill=fill, anchor=anchor)

    def wrapped(self, x, y, value, fnt, fill, max_width, line_height):
        words, line = value.split(" "), ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if fnt.getlength(candidate) > max_width * S and line:
                self.text(x, y, line, fnt, fill)
                y, line = y + line_height, word
            else:
                line = candidate
        self.text(x, y, line, fnt, fill)

    def chip(self, rect, label, fill, ink=WHITE, outline=None):
        x0, y0, x1, y1 = rect
        self.box(x0, y0, x1, y1, fill=fill, outline=outline, radius=7, width=2 if outline else 1)
        self.text((x0 + x1) / 2, (y0 + y1) / 2, label, F_CHIP, ink, "mm")


def lerp(a, b, k):
    return a + (b - a) * max(0.0, min(1.0, k))


def between(rect_a, rect_b, k):
    k = max(0.0, min(1.0, k))
    k = k * k * (3 - 2 * k)  # ease in and out
    return tuple(lerp(a, b, k) for a, b in zip(rect_a, rect_b))


PHASES = [
    (18, "1.  Request A is running on the thread. Its code sends a query to the database. The span's clock starts."),
    (20, "2.  While the database works, the thread is free. It takes the next request from the queue: B, a small one."),
    (18, "3.  B finishes quickly. The thread is free again and takes the next one: C, heavy work in code."),
    (22, "4.  After 10 ms the database is done. The answer for A comes back, but the thread is busy with C, so the answer joins the queue."),
    (34, "5.  The answer waits in the queue. The span's clock keeps counting."),
    (18, "6.  C ends. The thread is free, takes the answer from the queue and handles it. The span ends at 300 ms."),
    (24, "The database took 10 ms. The other 290 ms was the answer waiting for the thread."),
]

# Layout
DB = (40, 116, 250, 336)
THREAD = (290, 116, 690, 262)
QUEUE = (730, 116, 960, 336)
RUNNING = (306, 168, 674, 208)  # where the thread shows what it is running
PROGRESS = (306, 217, 674, 229)
SLOT_H, SLOT_GAP = 40, 9
LANE_Y = 304  # answers travel back along here, under the thread
T_X0, T_X1 = 232, 868  # timeline: 0 ms .. 300 ms
ROWS = {"thread": 376, "db": 414, "span": 452}
ROW_H = 22


def slot(index):
    y = QUEUE[1] + 52 + index * (SLOT_H + SLOT_GAP)
    return (QUEUE[0] + 16, y, QUEUE[2] - 16, y + SLOT_H)


def x_at(ms):
    return T_X0 + (T_X1 - T_X0) * ms / SPAN_END


def frame(phase, k):
    """Draw one frame. `phase` is 0..6, `k` is progress through it, 0..1."""
    c = Canvas()
    t = [0, lerp(0, B_END, k), lerp(B_END, 9, k), lerp(9, DB_DONE, k / 0.2), lerp(DB_DONE, SPAN_END, k ** 1.1), SPAN_END, SPAN_END][phase]
    sent = phase > 0 or k >= 0.3  # the query has left the thread, so the span's clock is running
    at_db = phase > 0 or k >= 0.8

    c.text(40, 18, "The trace says 300 ms. The database says 10 ms. Both are right.", F_TITLE)
    c.wrapped(40, 58, PHASES[phase][1], F_CAPTION, BLUE if phase < 6 else INK, 920, 22)

    # --- the database
    c.box(*DB, fill=PANEL, outline=LINE, radius=12)
    c.text(DB[0] + 16, DB[1] + 12, "The database", F_HEAD)
    db_chip = (DB[0] + 16, DB[1] + 46, DB[2] - 16, DB[1] + 86)
    if not at_db:
        c.chip(db_chip, "idle", WHITE, MUTED, LINE)
    elif t < DB_DONE:
        c.chip(db_chip, "Running A's query", GREEN)
    else:
        c.chip(db_chip, "Done", GREEN_SOFT, GREEN)
    db_ms = min(t, DB_DONE) if at_db else 0
    c.text(DB[0] + 16, DB[1] + 110, "Database's clock", F_SMALL, MUTED)
    c.text(DB[0] + 16, DB[1] + 128, f"{db_ms:.0f} ms", F_CLOCK, GREEN)
    if t >= DB_DONE:
        c.text(DB[0] + 16, DB[1] + 170, "stopped: its work is over", F_SMALL, MUTED)

    # --- the thread
    c.box(*THREAD, fill=PANEL, outline=LINE, radius=12)
    c.text(THREAD[0] + 16, THREAD[1] + 12, "The app's one thread (event loop)", F_HEAD)
    c.text(THREAD[0] + 16, THREAD[1] + 30, "now running:", F_SMALL, MUTED)

    def running(label, fill, ink=WHITE, outline=None):
        c.chip(RUNNING, label, fill, ink, outline)

    def progress(done_share, strong, soft):
        c.box(*PROGRESS, fill=soft, radius=6)
        c.box(PROGRESS[0], PROGRESS[1], lerp(PROGRESS[0] + 12, PROGRESS[2], done_share), PROGRESS[3], fill=strong, radius=6)

    free = lambda: running("free", WHITE, MUTED, LINE)
    c_share = (t - C_START) / (SPAN_END - C_START)
    moving = None  # a piece on its way between the queue and the thread, drawn last

    if phase == 0:
        running("Request A: sends the query", BLUE) if k < 0.8 else free()
    elif phase == 1:
        if k < 0.3:
            free()
            moving = (between(slot(0), RUNNING, k / 0.3), "Request B (small)", PURPLE)
        else:
            running("Request B: small work", PURPLE)
            progress((k - 0.3) / 0.7, PURPLE, PURPLE_SOFT)
    elif phase == 2:
        if k < 0.2:
            running("Request B: done", PURPLE_SOFT, PURPLE)
        elif k < 0.5:
            free()
            moving = (between(slot(0), RUNNING, (k - 0.2) / 0.3), "Request C (heavy)", ORANGE)
        else:
            running("Request C: heavy work in code", ORANGE)
            progress(c_share, ORANGE, ORANGE_SOFT)
    elif phase in (3, 4):
        running("Request C: heavy work in code", ORANGE)
        progress(c_share, ORANGE, ORANGE_SOFT)
    elif phase == 5 and k < 0.25:
        running("Request C: done", ORANGE_SOFT, ORANGE)
    elif phase == 5 and k < 0.6:
        free()
        moving = (between(slot(0), RUNNING, (k - 0.25) / 0.35), "Answer for request A", BLUE)
    else:
        running("Request A: handles the answer", BLUE)

    a_waits = at_db and not (phase == 6 or (phase == 5 and k >= 0.6))
    if a_waits:
        c.text(THREAD[0] + 16, THREAD[3] - 26, "Request A is off the thread, waiting for its answer", F_SMALL, MUTED)

    # --- the queue
    c.box(*QUEUE, fill=PANEL, outline=LINE, radius=12)
    c.text(QUEUE[0] + 16, QUEUE[1] + 12, "Queue: waiting for the thread", F_HEAD)
    c.text(QUEUE[0] + 16, QUEUE[1] + 30, "top = next", F_SMALL, MUTED)
    waiting = []
    if phase == 0:
        waiting = [("Request B (small)", PURPLE), ("Request C (heavy)", ORANGE)]
    elif phase == 1:
        if k < 0.3:  # C slides up as B leaves
            c.chip(between(slot(1), slot(0), k / 0.3), "Request C (heavy)", ORANGE)
        else:
            waiting = [("Request C (heavy)", ORANGE)]
    elif phase == 2 and k < 0.2:
        waiting = [("Request C (heavy)", ORANGE)]
    elif (phase == 3 and k >= 0.65) or phase == 4 or (phase == 5 and k < 0.25):
        waiting = [("Answer for request A", BLUE)]
        c.text((slot(1)[0] + slot(1)[2]) / 2, slot(1)[1] + 8, f"waiting for {t - DB_DONE:.0f} ms", F_BODY, INK, "ma")
    for index, (label, color) in enumerate(waiting):
        c.chip(slot(index), label, color)
    if not waiting and not (phase == 1 and k < 0.3):
        c.text(QUEUE[0] + 16, slot(0)[1] + 11, "(empty)", F_BODY, MUTED)

    # --- arrows: the three routes a piece can take. Grey when idle, dark while something is moving along them.
    query_moving = phase == 0 and 0.3 <= k < 0.8
    answer_moving = phase == 3 and 0.2 <= k < 0.65
    route = lambda active: (INK, 3) if active else (LINE, 2)
    gap_y = 150  # above the row of chips, so a passing chip does not hide the arrow

    color, width = route(query_moving)
    c.arrow(THREAD[0] - 5, gap_y, DB[2] + 5, gap_y, color, width)
    c.text((THREAD[0] + DB[2]) / 2, gap_y - 22, "query", F_SMALL, INK if query_moving else MUTED, "ma")

    color, width = route(bool(moving))
    c.arrow(QUEUE[0] - 5, gap_y, THREAD[2] + 5, gap_y, color, width)
    c.text((QUEUE[0] + THREAD[2]) / 2, gap_y - 22, "next", F_SMALL, INK if moving else MUTED, "ma")

    color, width = route(answer_moving)
    c.arrow(DB[2] + 6, LANE_Y - 28, QUEUE[0] - 6, LANE_Y - 28, color, width)
    c.text((DB[2] + QUEUE[0]) / 2, LANE_Y + 26, "answers come back and join the queue", F_SMALL, INK if answer_moving else MUTED, "ma")

    # --- pieces travelling
    if phase == 0 and 0.3 <= k < 0.8:  # the query: thread -> database
        x = lerp(THREAD[0] + 30, DB[2] - 50, (k - 0.3) / 0.5)
        c.chip((x - 40, 174, x + 40, 202), "query", BLUE)
    if phase == 3 and 0.2 <= k < 0.65:  # the answer: database -> queue, passing under the thread
        start = (DB[2] - 200, LANE_Y - 20, DB[2] - 2, LANE_Y + 20)
        below = (slot(0)[0], LANE_Y - 20, slot(0)[2], LANE_Y + 20)  # along the lane first, then up into the queue
        step = (k - 0.2) / 0.45
        position = between(start, below, step / 0.7) if step < 0.7 else between(below, slot(0), (step - 0.7) / 0.3)
        c.chip(position, "Answer for request A", BLUE)
    if moving:
        c.chip(*moving)

    # --- timeline
    c.text(40, ROWS["thread"] + 3, "Thread is running", F_BODY)
    c.text(40, ROWS["db"] + 3, "Database's log", F_BODY)
    c.text(40, ROWS["span"] + 3, "Query span in the trace", F_BODY)
    for y in ROWS.values():
        c.rect(T_X0, y, T_X1, y + ROW_H, PANEL)

    y = ROWS["thread"]
    if sent:
        c.rect(x_at(0), y, x_at(A_SENT), y + ROW_H, BLUE)
    if phase > 1 or (phase == 1 and k >= 0.3):
        c.rect(x_at(B_START), y, x_at(min(max(t, B_START + 0.5), B_END)), y + ROW_H, PURPLE)
    if t > C_START and (phase > 2 or k >= 0.5):
        c.rect(x_at(C_START), y, x_at(t), y + ROW_H, ORANGE)
    if phase == 6 or (phase == 5 and k >= 0.6):
        c.rect(x_at(SPAN_END) - 5, y, x_at(SPAN_END), y + ROW_H, BLUE)

    y = ROWS["db"]
    if db_ms > 0:
        c.rect(x_at(0), y, max(x_at(db_ms), x_at(0) + 2), y + ROW_H, GREEN)
    c.text(T_X1 + 12, y + 3, f"{db_ms:.0f} ms", F_HEAD, GREEN)

    y = ROWS["span"]
    span_ms = t if sent else 0
    if sent:
        c.rect(x_at(0), y, max(x_at(min(span_ms, DB_DONE)), x_at(0) + 2), y + ROW_H, BLUE)
    if span_ms > DB_DONE:
        c.rect(x_at(DB_DONE), y, x_at(span_ms), y + ROW_H, WAIT)
        if span_ms > 120:
            c.text((x_at(DB_DONE) + x_at(span_ms)) / 2, y + ROW_H / 2, "answer is waiting for the thread", F_SMALL, INK, "mm")
    c.text(T_X1 + 12, y + 3, f"{span_ms:.0f} ms", F_HEAD, BLUE)

    axis_y = ROWS["span"] + ROW_H + 8
    c.line(T_X0, axis_y, T_X1, axis_y, LINE)
    for ms in (0, 100, 200, 300):
        c.line(x_at(ms), axis_y, x_at(ms), axis_y + 5, LINE)
        c.text(x_at(ms), axis_y + 8, f"{ms} ms", F_SMALL, MUTED, "ma")
    if 0 < t < SPAN_END:
        c.line(x_at(t), ROWS["thread"] - 6, x_at(t), axis_y, INK, 2)

    if phase == 6:
        c.box(40, 528, 960, 564, fill=BLUE_SOFT, radius=8)
        c.text(500, 546, "10 ms in the database  +  290 ms waiting for the thread  =  300 ms on the span", F_HEAD, INK, "mm")

    return c.image.resize((W, H), Image.LANCZOS)


def main(out, check=False):
    frames, durations, starts = [], [], []
    for phase, (count, _caption) in enumerate(PHASES):
        starts.append(len(frames))
        for index in range(count):
            frames.append(frame(phase, index / max(1, count - 1)))
            durations.append(100)
    durations[-1] = 1200  # rest on the summary before the loop restarts
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    palette = [f.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    palette[0].save(out, save_all=True, append_images=palette[1:], duration=durations, loop=0, optimize=True)
    print(f"wrote {out}: {len(frames)} frames, {sum(durations) / 1000:.1f} s, {out.stat().st_size // 1024} KB")
    if check:  # a few stills, for checking the layout
        picks = {"1a": starts[0] + 2, "1b": starts[0] + 9, "2a": starts[1] + 3, "2b": starts[1] + 14, "3a": starts[2] + 6,
                 "3b": starts[2] + 15, "4a": starts[3] + 9, "4b": starts[3] + 19, "5": starts[4] + 20, "6a": starts[5] + 7, "7": len(frames) - 1}
        for name, index in picks.items():
            frames[index].save(out.with_name(f"_check-{name}.png"))


if __name__ == "__main__":
    main(sys.argv[1], check="--check" in sys.argv)

"""Character silhouettes with procedural poses, readable telegraphs.

No sprites: bodies are drawn as dark shapes with glowing eyes; poses are
computed from state + state timers, souls-readable (windups are visible).
"""

from __future__ import annotations

import math

import pygame

from slg.render.palette import PALETTE


def _glow(surface: pygame.Surface, pos: tuple[int, int], radius: int,
          color: tuple[int, int, int], alpha: int) -> None:
    if radius <= 0:
        return
    r = radius * 3
    glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    pygame.draw.circle(glow, (*color, alpha), (r, r), r)
    surface.blit(glow, (pos[0] - r, pos[1] - r), special_flags=pygame.BLEND_RGBA_ADD)


def _telegraph_ring(surface: pygame.Surface, pos: tuple[int, int],
                    progress: float, color: tuple[int, int, int]) -> None:
    """Expanding pulsing ring: 0..1 progress of the telegraph window."""
    radius = int(18 + progress * 34)
    pulse = 0.5 + 0.5 * math.sin(progress * 24.0)
    c = (*color, int(90 + 120 * pulse))
    ring = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
    pygame.draw.circle(ring, c, (radius + 4, radius + 4), radius, 3)
    surface.blit(ring, (pos[0] - radius - 4, pos[1] - radius - 4))


def _shadow(surface: pygame.Surface, pos: tuple[int, int], half_w: float) -> None:
    w = int(half_w * 1.6)
    shadow = pygame.Surface((w * 2, 10), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 90), (0, 0, w * 2, 10))
    surface.blit(shadow, (pos[0] - w, pos[1] - 5))


# ====================================================================== player

def draw_player(surface: pygame.Surface, player, to_screen, time: float) -> None:
    e = player.entity
    if not e.alive:
        _draw_player_dead(surface, e, to_screen)
        return
    sx, sy = to_screen(e.x, e.y, e.z)
    f = e.facing
    sil = PALETTE["silhouette"]
    rim = PALETTE["rim"]

    def P(x: float, y: float) -> tuple[int, int]:
        return (int(sx + f * x), int(sy + y))

    state = player.state
    t = player.state_timer

    if state == "roll":
        _draw_player_roll(surface, P, t, player.cfg.roll.duration, f)
        return

    bob = math.sin(time * 2.4) * 1.5 if state == "idle" else 0.0
    hip_y = 12 + bob
    shoulder_y = -10 + bob
    head = P(0, -21 + bob)

    # ---- legs ----
    if state == "run":
        phase = math.sin(t * 13.0)
        knee1 = P(6 * f * f + phase * 9, 20)
        foot1 = P(phase * 14, 27 - abs(phase) * 4)
        knee2 = P(-phase * 9, 20)
        foot2 = P(-phase * 14, 27 - abs(phase) * 4)
    elif state == "jump":
        up = -1 if e.vy < 0 else 1
        knee1, foot1 = P(5, 14 + up * 2), P(10, 20 + up * 4)
        knee2, foot2 = P(-4, 18), P(-8, 26)
    elif state == "heal":
        knee1, foot1 = P(8, 22), P(12, 27)
        knee2, foot2 = P(-6, 24), P(-10, 27)
    elif state == "hurt":
        knee1, foot1 = P(-4, 20), P(-9, 27)
        knee2, foot2 = P(5, 21), P(9, 27)
    else:
        knee1, foot1 = P(4, 20), P(6, 27)
        knee2, foot2 = P(-4, 20), P(-6, 27)
    hip = P(0, hip_y)
    pygame.draw.lines(surface, sil, False, [hip, knee1, foot1], 5)
    pygame.draw.lines(surface, sil, False, [hip, knee2, foot2], 5)

    # ---- torso ----
    shoulder = P(0, shoulder_y)
    lean = 0.0
    if state == "run":
        lean = 4.0
    elif state == "hurt":
        lean = -6.0
    elif state in ("attack_l", "attack_h"):
        lean = 6.0 if player.attack.phase in ("active", "recovery") else -4.0
    shoulder = P(lean, shoulder_y)
    pygame.draw.line(surface, sil, hip, shoulder, 8)
    pygame.draw.line(surface, rim, P(lean - 2, shoulder_y + 1), P(-2, hip_y - 2), 2)

    # ---- arms + weapon ----
    hand = _player_arm_pose(surface, player, P, shoulder, t, state)

    # ---- head ----
    pygame.draw.circle(surface, sil, head, 7)
    pygame.draw.circle(surface, rim, (head[0] - 2 * f, head[1] - 2), 6, 1)
    eye = P(3, -22 + bob)
    _glow(surface, eye, 2, PALETTE["eyes"], 160)
    pygame.draw.circle(surface, PALETTE["eyes"], eye, 2)

    # ---- heal flask glow ----
    if state == "heal":
        pulse = 0.5 + 0.5 * math.sin(t * 10.0)
        _glow(surface, hand, int(4 + pulse * 5), PALETTE["heal_glow"], 150)
        pygame.draw.circle(surface, PALETTE["heal_glow"], hand, 3)

    _shadow(surface, (sx, int(sy + e.half_h)), e.half_w)


def _player_arm_pose(surface, player, P, shoulder, t, state):
    """Draw arms + blade; returns the weapon-side hand position."""
    sil = PALETTE["silhouette"]
    blade_len = 30
    if state in ("attack_l", "attack_h"):
        atk = player.attack
        phase = atk.phase
        prog = atk.timer / max(0.001, (atk.attack.windup if phase == "windup"
                                       else atk.attack.active if phase == "active"
                                       else atk.attack.recovery))
        prog = min(1.0, max(0.0, prog))
        if phase == "windup":
            ang = math.radians(-150 + prog * 20)  # raised behind
            hand = P(math.cos(ang) * 16, math.sin(ang) * 16 + 2)
        elif phase == "active":
            ang = math.radians(-40 - prog * 70)   # swung down-front
            hand = P(math.cos(ang) * 20, math.sin(ang) * 20 + 2)
        else:
            ang = math.radians(30)                # held low-front
            hand = P(math.cos(ang) * 18, math.sin(ang) * 18 + 2)
        pygame.draw.lines(surface, sil, False, [shoulder, P(0, -2), hand], 4)
        # blade
        wang = ang - math.radians(50)
        tip = (hand[0] + f_sign(player) * math.cos(wang) * blade_len,
               hand[1] + math.sin(wang) * blade_len)
        pygame.draw.line(surface, PALETTE["bone"], hand,
                         (int(tip[0]), int(tip[1])), 3)
        if phase == "active":
            _glow(surface, (int(tip[0]), int(tip[1])), 5, PALETTE["bone"], 90)
        off_hand = P(-6, 4)
        pygame.draw.lines(surface, sil, False, [shoulder, P(-4, 6), off_hand], 3)
        return hand
    if state == "run":
        swing = math.sin(t * 13.0) * 8
        hand = P(8 + swing, 2)
        pygame.draw.lines(surface, sil, False, [shoulder, P(4, 6), hand], 4)
        pygame.draw.lines(surface, sil, False, [shoulder, P(-4, 6), P(-6 - swing, 4)], 3)
        # blade resting on back
        pygame.draw.line(surface, PALETTE["bone"], P(-10, -14), P(6, -26), 3)
        return hand
    if state == "heal":
        hand = P(10, 4)
        pygame.draw.lines(surface, sil, False, [shoulder, P(6, 4), hand], 4)
        pygame.draw.lines(surface, sil, False, [shoulder, P(-5, 8), P(-9, 12)], 3)
        return hand
    if state == "hurt":
        hand = P(-10, -6)
        pygame.draw.lines(surface, sil, False, [shoulder, P(-6, -2), hand], 4)
        pygame.draw.lines(surface, sil, False, [shoulder, P(-3, 6), P(-8, 2)], 3)
        return hand
    # idle / jump
    hand = P(7, 6 + math.sin(t * 2.0) * 1.5)
    pygame.draw.lines(surface, sil, False, [shoulder, P(4, 6), hand], 4)
    pygame.draw.lines(surface, sil, False, [shoulder, P(-4, 7), P(-7, 9)], 3)
    pygame.draw.line(surface, PALETTE["bone"], P(-10, -14), P(6, -26), 3)
    return hand


def f_sign(player) -> int:
    return player.entity.facing


def _draw_player_roll(surface, P, t, duration, f):
    sil = PALETTE["silhouette"]
    r = 15
    ang = (t / duration) * math.pi * 2.0 * 2 * f
    c = P(0, 10)
    pygame.draw.circle(surface, sil, c, r)
    for i in range(3):
        a = ang + i * math.pi / 1.5
        pygame.draw.line(surface, PALETTE["rim"], c,
                         (int(c[0] + math.cos(a) * (r - 4)),
                          int(c[1] + math.sin(a) * (r - 4))), 2)
    _glow(surface, (int(c[0] + math.cos(ang) * 6), int(c[1] + math.sin(ang) * 6)),
          2, PALETTE["eyes"], 120)


def _draw_player_dead(surface, e, to_screen):
    sx, sy = to_screen(e.x, e.y, e.z)
    sil = PALETTE["silhouette"]
    pygame.draw.ellipse(surface, sil, (sx - 20, sy + e.half_h - 12, 40, 12))
    pygame.draw.circle(surface, sil, (sx + 22, sy + e.half_h - 8), 6)


# ====================================================================== crawler

def draw_crawler(surface, crawler, to_screen, time):
    e = crawler.entity
    if not e.alive:
        return
    sx, sy = to_screen(e.x, e.y, e.z)
    f = e.facing
    sil = PALETTE["silhouette"]
    state = crawler.state
    t = crawler.state_timer

    rear = 0.0
    stretch = 1.0
    if state == "telegraph":
        rear = -6.0 * min(1.0, t / 0.2)
    elif state == "strike":
        stretch = 1.35
    elif state == "stagger":
        rear = 4.0

    def P(x, y):
        return (int(sx + f * (x + rear)), int(sy + y))

    cx, cy = P(0, 0)
    rx, ry = int(23 * stretch), 14
    body = pygame.Rect(cx - rx, cy - ry, rx * 2, ry * 2)
    pygame.draw.ellipse(surface, sil, body)
    pygame.draw.ellipse(surface, PALETTE["rim"], body, 1)

    # spikes
    for i in range(-2, 3):
        bx = cx + int(f * i * 8 * stretch)
        pygame.draw.polygon(surface, sil, [
            (bx - 3, cy - ry + 4), (bx + 3, cy - ry + 4), (bx + f, cy - ry - 7),
        ])

    # legs
    walk = math.sin(time * 9.0) * 4 if state in ("patrol", "aggro") else math.sin(t * 20) * 3
    for i, off in enumerate((-14, -5, 5, 14)):
        lx = cx + int(f * off * stretch)
        phase = walk if i % 2 == 0 else -walk
        pygame.draw.lines(surface, sil, False, [
            (lx, cy + 4), (lx + int(phase), cy + 12), (lx + int(phase * 1.5), cy + 15),
        ], 3)

    # eyes + mouth
    eye = P(14 * stretch, -3)
    pygame.draw.circle(surface, PALETTE["eyes"], eye, 2)
    pygame.draw.circle(surface, PALETTE["eyes"], P(10 * stretch, -6), 2)
    if state == "telegraph":
        prog = min(1.0, t / crawler.c.telegraph)
        _telegraph_ring(surface, (sx, sy), prog, PALETTE["telegraph"])
        mouth = P(20 * stretch, 2)
        _glow(surface, mouth, int(2 + prog * 5), PALETTE["danger"], 160)
    _shadow(surface, (sx, int(sy + e.half_h)), e.half_w)


# ====================================================================== spitter

def draw_spitter(surface, spitter, to_screen, time):
    e = spitter.entity
    if not e.alive:
        return
    sx, sy = to_screen(e.x, e.y, e.z)
    f = e.facing
    sil = PALETTE["silhouette"]
    state = spitter.state
    t = spitter.state_timer

    inflate = 1.0
    if state == "telegraph":
        inflate = 1.0 + 0.3 * min(1.0, t / spitter.s.telegraph)
    elif state == "recover":
        inflate = 1.15

    rx = int(19 * inflate)
    ry = int(20 * inflate)
    body = pygame.Rect(sx - rx, sy - ry, rx * 2, ry * 2)
    pygame.draw.ellipse(surface, sil, body)
    pygame.draw.ellipse(surface, PALETTE["rim"], body, 1)

    # wobble sacs
    for i in range(3):
        a = time * 1.7 + i * 2.1
        ox = int(math.cos(a) * 6)
        oy = int(math.sin(a) * 3)
        pygame.draw.circle(surface, PALETTE["moss"],
                           (sx - rx // 2 + ox, sy + ry // 3 + oy), 3)

    # legs
    for off in (-10, 10):
        pygame.draw.lines(surface, sil, False, [
            (sx + off, sy + ry - 4), (sx + off + (3 if off > 0 else -3), sy + e.half_h),
        ], 3)

    # orifice
    mouth = (sx + f * rx - f * 3, sy - 2)
    pygame.draw.circle(surface, (0, 0, 0), mouth, 4)
    if state == "telegraph":
        prog = min(1.0, t / spitter.s.telegraph)
        _telegraph_ring(surface, (sx, sy), prog, PALETTE["telegraph"])
        _glow(surface, mouth, int(2 + prog * 6), PALETTE["spore"], 170)
    else:
        pygame.draw.circle(surface, PALETTE["spore_dim"], mouth, 2)
    _shadow(surface, (sx, int(sy + e.half_h)), e.half_w)


# ====================================================================== shard

def draw_shard(surface, shard, to_screen, time):
    e = shard.entity
    if not e.alive:
        return
    sx, sy = to_screen(e.x, e.y, e.z)
    f = e.facing
    sil = PALETTE["silhouette"]
    state = shard.state
    t = shard.state_timer
    by = int(sy + e.half_h)

    if state == "lunge":
        # a stretched blade of glass racing through the air
        pts = [
            (sx - f * 30, int(sy + 2)), (sx - f * 6, int(sy - 9)),
            (sx + f * 26, int(sy - 1)), (sx - f * 6, int(sy + 9)),
        ]
        pygame.draw.polygon(surface, sil, pts)
        pygame.draw.polygon(surface, PALETTE["bone"], pts, 1)
        _glow(surface, (sx + f * 12, sy), 3, PALETTE["spore"], 130)
        pygame.draw.line(surface, PALETTE["spore"], (sx - f * 40, sy), (sx - f * 26, sy), 1)
    else:
        # a cluster of standing crystals (dormant = smaller, part of the scenery)
        tall = 30 if state != "dormant" else 22
        shards = ((0, tall, 9), (-11, tall * 0.7, 7), (10, tall * 0.8, 7))
        for ox, hgt, half in shards:
            tip = (sx + int(f * ox), by - int(hgt))
            left = (sx + int(f * ox) - half, by)
            right = (sx + int(f * ox) + half, by)
            pygame.draw.polygon(surface, sil, [left, tip, right])
            pygame.draw.line(surface, PALETTE["rim"], tip,
                             (right[0], right[1] - 2), 1)
        if state == "recover":
            # spent / cracked: dim tilted stubs
            pygame.draw.line(surface, PALETTE["spore_dim"], (sx - 10, by - 4), (sx + 10, by - 10), 1)

    if state == "telegraph":
        prog = min(1.0, t / shard.s.telegraph)
        _telegraph_ring(surface, (sx, sy), prog, PALETTE["telegraph"])
        _glow(surface, (sx, int(sy - 6)), int(3 + prog * 7), PALETTE["bone"], int(140 + prog * 110))
        pygame.draw.line(surface, PALETTE["bone"], (sx, int(sy - 30)), (sx + f * 6, int(sy - 20)), 2)
    elif state == "dormant":
        _glow(surface, (sx, int(sy - 4)), 2, PALETTE["spore_dim"], 40)
    _shadow(surface, (sx, by), e.half_w)


# ====================================================================== orb

def draw_orb(surface, orb, to_screen, time):
    """Ball lightning: a crackling teal core with restless arcs."""
    e = orb.entity
    if not e.alive:
        return
    sx, sy = to_screen(e.x, e.y, e.z)
    core = PALETTE["spore"]
    hot = PALETTE["eyes"]
    r = 15

    if orb.state == "fall":
        # a bright tail while it drops toward the arena
        pygame.draw.line(surface, PALETTE["spore_dim"],
                         (sx, sy - 26), (sx, sy - 10), 4)

    _glow(surface, (sx, sy), r + 5, core, 140)

    for i in range(6):
        a = time * 5.0 + i * math.tau / 6.0
        reach = r + 4 + int((math.sin(time * 13.0 + i * 2.1) + 1.0) * 3)
        x1 = sx + int(math.cos(a) * reach)
        y1 = sy + int(math.sin(a) * reach)
        x2 = sx + int(math.cos(a + 0.45) * (reach + 8))
        y2 = sy + int(math.sin(a + 0.45) * (reach + 8))
        color = PALETTE["terrain_rim"] if i % 2 else core
        pygame.draw.line(surface, color, (x1, y1), (x2, y2), 1)

    pygame.draw.circle(surface, core, (sx, sy), r)
    pygame.draw.circle(surface, hot, (sx, sy), r - 5)
    pygame.draw.circle(surface, PALETTE["bone"], (sx + 2, sy - 2), 3)
    if math.sin(time * 17.0 + e.x * 0.1) > 0.6:
        pygame.draw.circle(surface, PALETTE["bone"], (sx - 4, sy + 3), 2)

    _shadow(surface, (sx, int(sy + e.half_h + 12)), e.half_w * 0.5)


# ====================================================================== boss

def draw_boss(surface, boss, to_screen, time):
    if boss.kind == "blade":
        _draw_blade(surface, boss, to_screen, time)
    elif boss.kind == "prism":
        _draw_prism(surface, boss, to_screen, time)
    elif boss.kind == "keeper":
        _draw_keeper(surface, boss, to_screen, time)
    else:
        _draw_devourer(surface, boss, to_screen, time)


def draw_noise_ring(surface, player, to_screen) -> None:
    """Expanding ground ring showing the player's last noisy step."""
    pulse = getattr(player, "noise_pulse", 0.0)
    if pulse <= 0.0:
        return
    e = player.entity
    sx, sy = to_screen(e.x, e.y + e.half_h, 0)
    frac = min(1.0, pulse / 0.35)
    rw = int(10 + frac * 34)
    rh = max(5, rw // 2)
    alpha = int(150 * (1.0 - frac))
    ring = pygame.Surface((rw * 2 + 4, rh * 2 + 4), pygame.SRCALPHA)
    pygame.draw.ellipse(ring, (*PALETTE["spore"], alpha), (2, 2, rw * 2, rh * 2), 2)
    surface.blit(ring, (sx - rw - 2, sy - rh - 2))



def _draw_devourer(surface, boss, to_screen, time):
    e = boss.entity
    if not e.alive:
        return
    sx, sy = to_screen(e.x, e.y, e.z)
    f = e.facing
    sil = PALETTE["silhouette"]
    state = boss.state
    t = boss.state_timer
    phase2 = boss.phase == 2
    eye_color = PALETTE["eyes_boss"] if phase2 else PALETTE["eyes"]

    def P(x, y):
        return (int(sx + f * x), int(sy + y))

    breathe = math.sin(time * (2.2 if phase2 else 1.4)) * 3
    hip = P(0, 34)
    shoulder = P(0, -22 + breathe)
    head = P(0, -40 + breathe)

    # legs
    stance = 26
    pygame.draw.lines(surface, sil, False, [hip, P(-stance * 0.6, 18), P(-stance, 58)], 10)
    pygame.draw.lines(surface, sil, False, [hip, P(stance * 0.6, 18), P(stance, 58)], 10)

    # torso: massive mass
    pygame.draw.polygon(surface, sil, [
        P(-30, -26 + breathe), P(30, -26 + breathe), P(24, 20), P(-24, 20),
    ])
    pygame.draw.polygon(surface, PALETTE["rim"], [
        P(-30, -26 + breathe), P(-26, -24 + breathe), P(-20, 16), P(-24, 20),
    ], 1)

    # head + horn crown
    pygame.draw.circle(surface, sil, head, 12)
    for i, (hx, hy, hl) in enumerate(((-8, -8, 16), (0, -11, 22), (8, -8, 16))):
        tip = P(hx * 1.6, -40 + breathe + hy - hl)
        pygame.draw.polygon(surface, sil, [
            P(hx - 3, -40 + breathe + hy), P(hx + 3, -40 + breathe + hy), tip,
        ])

    # eyes cluster
    for ex, ey in ((-5, -42), (0, -44), (5, -42), (-2, -38), (3, -38)):
        pos = P(ex, ey + breathe)
        pygame.draw.circle(surface, eye_color, pos, 2)
    _glow(surface, P(0, -42 + breathe), 6, eye_color, 90)

    # arms + pattern poses
    _boss_arms(surface, boss, P, shoulder, state, t, phase2, time)

    if state == "telegraph":
        prog = min(1.0, t / max(0.001, boss._pattern_telegraph()))
        _telegraph_ring(surface, (sx, sy), prog, PALETTE["telegraph"])
        _glow(surface, (sx, sy), int(8 + prog * 14), PALETTE["danger"], 60)
    if state == "roar":
        _glow(surface, head, int(10 + math.sin(t * 18) * 6), eye_color, 120)
    _shadow(surface, (sx, int(sy + e.half_h)), e.half_w)


def _boss_arms(surface, boss, P, shoulder, state, t, phase2, time):
    sil = PALETTE["silhouette"]
    pattern = boss.pattern
    raise_amount = 0.0
    if state == "telegraph" and pattern == "slam":
        raise_amount = min(1.0, t / max(0.001, boss._pattern_telegraph()))
    elif state == "active" and pattern == "slam":
        raise_amount = max(0.0, 1.0 - t / max(0.001, boss.b.slam_active))

    def arm(side: int, back: bool):
        sh = P(side * 26, -20)
        if state == "telegraph" and pattern == "slam":
            elbow = P(side * (30 + raise_amount * 10), -34 - raise_amount * 26)
            hand = P(side * (34 + raise_amount * 14), -50 - raise_amount * 40)
        elif state == "active" and pattern == "slam":
            elbow = P(side * 34, 6)
            hand = P(side * 40, 34)
        elif state == "telegraph" and pattern == "sweep" and back:
            elbow = P(side * 20, -6)
            hand = P(-side * 30, -14)
        elif state == "active" and pattern == "sweep" and back:
            elbow = P(side * 34, -4)
            hand = P(side * 78, 8)
        elif state == "roar":
            elbow = P(side * 36, -18)
            hand = P(side * 52, -34)
        else:
            sway = math.sin(time * 1.3 + side) * 3
            elbow = P(side * 30, 4 + sway)
            hand = P(side * 36, 26 + sway)
        pygame.draw.lines(surface, sil, False, [sh, elbow, hand], 9)
        # claws
        for i in (-1, 0, 1):
            pygame.draw.line(surface, PALETTE["bone"], hand,
                             (hand[0] + i * 5, hand[1] + 10), 2)
        return hand

    arm(1, back=False)
    arm(-1, back=True)

    # chest orifice for volley
    if pattern == "volley" and state in ("telegraph", "active"):
        prog = min(1.0, t / max(0.001, boss._pattern_telegraph() if state == "telegraph" else 0.3))
        mouth = P(0, -6)
        pygame.draw.circle(surface, (0, 0, 0), mouth, 6)
        _glow(surface, mouth, int(3 + prog * 7), PALETTE["spore"], 170)


# ====================================================================== blade

def _draw_blade(surface, boss, to_screen, time):
    """Melee twin: lean silhouette with a long glass blade instead of a hand."""
    e = boss.entity
    if not e.alive:
        return
    sx, sy = to_screen(e.x, e.y, e.z)
    f = e.facing
    sil = PALETTE["silhouette"]
    state = boss.state
    t = boss.state_timer
    phase2 = boss.phase == 2
    eye_color = PALETTE["eyes_boss"] if phase2 else PALETTE["eyes"]

    def P(x, y):
        return (int(sx + f * x), int(sy + y))

    breathe = math.sin(time * (2.6 if phase2 else 1.8)) * 2
    hip = P(0, 26)
    shoulder = P(0, -18 + breathe)
    head = P(0, -32 + breathe)

    # legs
    pygame.draw.lines(surface, sil, False, [hip, P(-11, 10), P(-18, 44)], 7)
    pygame.draw.lines(surface, sil, False, [hip, P(11, 10), P(18, 44)], 7)

    # narrow torso
    pygame.draw.polygon(surface, sil, [
        P(-14, -22 + breathe), P(14, -22 + breathe), P(10, 22), P(-10, 22),
    ])
    pygame.draw.lines(surface, PALETTE["rim"], False,
                      [P(-13, -21 + breathe), P(-9, 18)], 1)

    # head
    pygame.draw.circle(surface, sil, head, 9)
    pygame.draw.lines(surface, sil, False, [
        P(-6, -33 + breathe), P(0, -44 + breathe), P(6, -33 + breathe),
    ], 3)
    pygame.draw.circle(surface, eye_color, P(4, -33 + breathe), 2)
    _glow(surface, P(4, -33 + breathe), 3, eye_color, 90)

    # blade arm poses
    raise_amt = 0.0
    swing_amt = 0.0
    if state == "telegraph" and boss.pattern == "slam":
        raise_amt = min(1.0, t / max(0.001, boss._pattern_telegraph()))
    elif state == "active" and boss.pattern == "slam":
        raise_amt = max(0.0, 1.0 - t / max(0.001, boss.b.slam_active))
    elif state == "telegraph" and boss.pattern == "sweep":
        swing_amt = -min(1.0, t / max(0.001, boss._pattern_telegraph()))
    elif state == "active" and boss.pattern == "sweep":
        swing_amt = 1.0

    hand = P(20 + raise_amt * 6, -10 - raise_amt * 34 + swing_amt * 30)
    elbow = P(16, -24 + breathe)
    pygame.draw.lines(surface, sil, False, [shoulder, elbow, hand], 5)
    blade_dir = math.radians(-120 + raise_amt * -40 + (swing_amt + 1.0) * 55)
    blade_tip = (int(hand[0] + f * math.cos(blade_dir) * 58),
                 int(hand[1] + math.sin(blade_dir) * 58))
    pygame.draw.line(surface, PALETTE["bone"], hand, blade_tip, 3)
    pygame.draw.line(surface, PALETTE["spore"], hand, blade_tip, 1)
    if state == "active":
        _glow(surface, blade_tip, 4, PALETTE["bone"], 110)

    # off hand
    pygame.draw.lines(surface, sil, False, [shoulder, P(-12, -6), P(-16, 8)], 4)

    if state == "telegraph":
        prog = min(1.0, t / max(0.001, boss._pattern_telegraph()))
        _telegraph_ring(surface, (sx, sy), prog, PALETTE["telegraph"])
    if state == "roar":
        _glow(surface, head, int(10 + math.sin(t * 18) * 6), eye_color, 130)
    _shadow(surface, (sx, int(sy + e.half_h)), e.half_w)


# ====================================================================== prism

def _draw_prism(surface, boss, to_screen, time):
    """Ranged twin: a floating crystal core trailing orbiting splinters."""
    e = boss.entity
    if not e.alive:
        return
    sx, sy = to_screen(e.x, e.y, e.z)
    f = e.facing
    sil = PALETTE["silhouette"]
    state = boss.state
    t = boss.state_timer
    phase2 = boss.phase == 2
    eye_color = PALETTE["eyes_boss"] if phase2 else PALETTE["eyes"]
    hover = math.sin(time * (2.4 if phase2 else 1.6)) * 4

    cx, cy = sx, int(sy + hover)
    charge = 0.0
    if state == "telegraph" and boss.pattern == "volley":
        charge = min(1.0, t / max(0.001, boss._pattern_telegraph()))
    elif state == "active" and boss.pattern == "volley":
        charge = 1.0

    # orbiting splinters
    n = 5 if not phase2 else 7
    for i in range(n):
        a = time * 1.2 + i * (math.tau / n)
        ox = int(math.cos(a) * (34 + charge * 6))
        oy = int(math.sin(a) * (18 + charge * 4)) + hover
        pts = [(cx + ox, cy + oy - 6), (cx + ox + 4, cy + oy + 4), (cx + ox - 4, cy + oy + 4)]
        pygame.draw.polygon(surface, sil, pts)
        pygame.draw.polygon(surface, PALETTE["rim"], pts, 1)

    # main crystal: tall faceted bipyramid
    h = 48
    w = 20
    pts = [(cx, cy - h), (cx + w, cy - 6), (cx + 10, cy + h), (cx - 10, cy + h), (cx - w, cy - 6)]
    pygame.draw.polygon(surface, sil, pts)
    pygame.draw.lines(surface, PALETTE["rim"], True, pts, 2)
    pygame.draw.line(surface, PALETTE["terrain_rim"], (cx, cy - h + 4), (cx, cy + h - 6), 1)

    # core
    core_r = 6 + int(charge * 5)
    _glow(surface, (cx, cy - 4), core_r, PALETTE["spore"], int(90 + charge * 100))
    pygame.draw.circle(surface, PALETTE["bone"], (cx, cy - 4), 3)
    pygame.draw.circle(surface, eye_color, (cx + f * 2, cy - 8), 2)

    if state == "telegraph":
        prog = min(1.0, t / max(0.001, boss._pattern_telegraph()))
        _telegraph_ring(surface, (sx, sy), prog, PALETTE["telegraph"])
    if state == "roar":
        _glow(surface, (cx, cy - 8), int(12 + math.sin(t * 16) * 6), eye_color, 140)
    _shadow(surface, (sx, int(sy + e.half_h)), e.half_w * 0.7)


# ====================================================================== keeper

def _keeper_floor(surface, boss, to_screen, phase2: bool) -> None:
    """Floor-level telegraphs and hazards: drawn before the body."""
    e = boss.entity
    state = boss.state
    t = boss.state_timer
    pattern = boss.pattern
    b = boss.b
    floor = e.y + e.half_h
    danger = PALETTE["danger"]
    tele = PALETTE["telegraph"]

    if pattern == "lantern_slam" and state in ("telegraph", "active"):
        gx, gy = to_screen(boss.attack_target, floor, 0)
        r = int(b.slam_range)
        ry = max(6, r // 2)
        if state == "telegraph":
            prog = min(1.0, t / max(0.001, boss._pattern_telegraph()))
        else:
            prog = 1.0
        disc = pygame.Surface((r * 2 + 4, ry * 2 + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(disc, (*danger, int(35 + 65 * prog)), (2, 2, r * 2, ry * 2))
        pygame.draw.ellipse(disc, (*tele, 190), (2, 2, r * 2, ry * 2), 3)
        surface.blit(disc, (gx - r - 2, gy - ry - 2))

    if pattern == "call_orbs" and state == "telegraph":
        for tx in boss.drop_targets:
            gx, gy = to_screen(tx, floor, 0)
            r = int(b.orb_zone_radius)
            ry = max(4, r // 2)
            mark = pygame.Surface((r * 2 + 4, ry * 2 + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(mark, (*tele, 120), (2, 2, r * 2, ry * 2), 2)
            surface.blit(mark, (gx - r - 2, gy - ry - 2))

    for drop in boss.orb_drops:
        ox, oy = to_screen(drop.x, drop.y, 0)
        pygame.draw.line(surface, PALETTE["telegraph"], (ox, oy - 34), (ox, oy - 6), 2)
        pygame.draw.circle(surface, PALETTE["bone"], (ox, oy), 5)
        _glow(surface, (ox, oy), 9, tele, 150)

    for zone in boss.shock_zones:
        zx, zy = to_screen(zone.x, zone.y, 0)
        fade = max(0.0, zone.life / max(0.001, zone.max_life))
        r = int(zone.radius)
        ry = max(4, r // 2)
        pool = pygame.Surface((r * 2 + 4, ry * 2 + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(pool, (*tele, int(90 * fade)), (2, 2, r * 2, ry * 2))
        pygame.draw.ellipse(pool, (*danger, int(180 * fade)), (2, 2, r * 2, ry * 2), 2)
        surface.blit(pool, (zx - r - 2, zy - ry - 2))
        _glow(surface, (zx, zy), 6, tele, int(70 * fade))

    if pattern == "echo_wave" and state in ("active", "recover") and boss.echo_radius > 0.0:
        gx, gy = to_screen(e.x, floor, 0)
        r = int(boss.echo_radius)
        ry = max(5, r // 2)
        ring = pygame.Surface((r * 2 + 8, ry * 2 + 8), pygame.SRCALPHA)
        pygame.draw.ellipse(ring, (*tele, 200), (4, 4, r * 2, ry * 2), 4)
        surface.blit(ring, (gx - r - 4, gy - ry - 4))


def _draw_keeper(surface, boss, to_screen, time):
    """Blind keeper: stooped silhouette, bone mask without eyes, lantern staff."""
    e = boss.entity
    if not e.alive:
        return
    _keeper_floor(surface, boss, to_screen, boss.phase == 2)

    sx, sy = to_screen(e.x, e.y, e.z)
    f = e.facing
    sil = PALETTE["silhouette"]
    state = boss.state
    t = boss.state_timer
    pattern = boss.pattern
    phase2 = boss.phase == 2
    lamp = PALETTE["telegraph"] if phase2 else PALETTE["spore"]
    bone = PALETTE["bone"]

    def P(x, y):
        return (int(sx + f * x), int(sy + y))

    breathe = math.sin(time * (2.2 if phase2 else 1.4)) * 2
    hip = P(0, 30)
    shoulder = P(-2, -20 + breathe)
    head = P(12, -34 + breathe)

    # legs: bent, wide stance
    pygame.draw.lines(surface, sil, False, [hip, P(-10, 28), P(-16, 62)], 9)
    pygame.draw.lines(surface, sil, False, [hip, P(12, 26), P(6, 62)], 9)

    # stooped torso
    pygame.draw.polygon(surface, sil, [
        P(-20, -22 + breathe), P(16, -30 + breathe),
        P(22, 12), P(-16, 20),
    ])
    pygame.draw.lines(surface, PALETTE["rim"], False,
                      [P(-19, -20 + breathe), P(-15, 14)], 1)

    # bone mask, no eyes
    pygame.draw.circle(surface, sil, head, 11)
    mask = [(head[0] + x, head[1] + y) for x, y in
            ((-2, -9), (8, -6), (10, 4), (2, 10), (-6, 8), (-8, 0))]
    pygame.draw.polygon(surface, bone, mask)
    pygame.draw.circle(surface, PALETTE["flesh_dark"], P(16, -35 + breathe), 2)
    pygame.draw.circle(surface, PALETTE["flesh_dark"], P(8, -36 + breathe), 2)
    _glow(surface, head, 4, PALETTE["rim"], 40)

    # staff pose
    raise_amt = 0.0
    slam_amt = 0.0
    echo_amt = 0.0
    if state == "telegraph" and pattern == "lantern_slam":
        raise_amt = min(1.0, t / max(0.001, boss._pattern_telegraph()))
    elif state == "active" and pattern == "lantern_slam":
        slam_amt = min(1.0, t / max(0.001, boss.b.slam_active))
    elif state == "telegraph" and pattern == "echo_wave":
        echo_amt = min(1.0, t / max(0.001, boss._pattern_telegraph()))
    elif state == "active" and pattern == "echo_wave":
        echo_amt = 1.0
    elif state in ("telegraph", "active") and pattern == "call_orbs":
        raise_amt = 0.6

    if slam_amt > 0.0:
        hand = P(22 + slam_amt * 12, -12 + slam_amt * 30)
        tip = (hand[0] + int(f * (22 + slam_amt * 12)), hand[1] + 22 + int(slam_amt * 18))
    elif raise_amt > 0.0:
        hand = P(16 - raise_amt * 4, -18 - raise_amt * 20)
        tip = (hand[0] - int(f * 6), hand[1] - 50 - int(raise_amt * 20))
    elif echo_amt > 0.0:
        hand = P(20 + echo_amt * 4, -14 + breathe)
        tip = (hand[0] + int(f * (42 + echo_amt * 22)), hand[1] - 2)
    else:
        sway = math.sin(time * 1.2) * 2
        hand = P(24, -10 + breathe + sway)
        tip = (hand[0] + int(f * 6), hand[1] - 54)

    pygame.draw.lines(surface, sil, False, [shoulder, P(20, -12 + breathe), hand], 6)
    pygame.draw.line(surface, sil, hand, tip, 5)
    # lantern
    lr = 6 if not phase2 else 7
    pygame.draw.circle(surface, bone, tip, lr)
    pygame.draw.circle(surface, lamp, tip, max(2, lr - 3))
    pulse = 0.5 + 0.5 * math.sin(time * (9.0 if phase2 else 5.0))
    _glow(surface, tip, int(8 + pulse * (7 if phase2 else 3)), lamp, 150)

    # off arm
    pygame.draw.lines(surface, sil, False, [shoulder, P(-16, -2), P(-20, 14)], 5)

    if state == "telegraph":
        prog = min(1.0, t / max(0.001, boss._pattern_telegraph()))
        _telegraph_ring(surface, (sx, sy), prog, PALETTE["telegraph"])
    if state == "stagger":
        pygame.draw.circle(surface, PALETTE["rim"], head, 13, 2)
    if state == "roar":
        _glow(surface, head, int(10 + math.sin(t * 18) * 6), lamp, 130)
    _shadow(surface, (sx, int(sy + e.half_h)), e.half_w * 0.8)


# ====================================================================== misc

def draw_projectile(surface: pygame.Surface, projectile, to_screen, time):
    x, y = to_screen(projectile.x, projectile.y, projectile.z)
    pulse = 0.5 + 0.5 * math.sin(time * 14.0 + projectile.x * 0.05)
    r = int(projectile.radius)
    _glow(surface, (x, y), r + int(pulse * 3), PALETTE["spore"], 140)
    pygame.draw.circle(surface, PALETTE["spore"], (x, y), r)
    pygame.draw.circle(surface, PALETTE["silhouette"], (x, y), max(2, r - 3))


def draw_checkpoint(surface: pygame.Surface, checkpoint, activated: bool,
                    to_screen, time: float) -> None:
    x, y = to_screen(checkpoint.x, checkpoint.y, 0.0)
    color = PALETTE["spore"] if activated else PALETTE["spore_dim"]
    pulse = 0.5 + 0.5 * math.sin(time * (3.0 if activated else 1.2))
    # stalk
    pygame.draw.lines(surface, PALETTE["moss"], False,
                       [(x, y), (x - 3, y - 18), (x + 2, y - 34)], 4)
    # heart orb
    r = 7 + int(pulse * 3)
    if activated:
        _glow(surface, (x + 2, y - 40), r + 6, color, 120)
    pygame.draw.circle(surface, color, (x + 2, y - 40), r)
    pygame.draw.circle(surface, PALETTE["bone"], (x + 2, y - 40), max(2, r - 4))


# ====================================================================== hub


def draw_portal(surface: pygame.Surface, portal, to_screen, time: float) -> None:
    """A return gate: two dark pillars, a lintel and a shimmering veil."""
    x, y = to_screen(portal.x, portal.y, 0.0)
    sil = PALETTE["silhouette"]
    color = PALETTE["spore"]
    pulse = 0.5 + 0.5 * math.sin(time * 2.2 + portal.x * 0.01)
    top = y - 78
    base = y + 28
    # veil between the pillars
    veil = pygame.Surface((30, base - top), pygame.SRCALPHA)
    pygame.draw.rect(veil, (*color, int(34 + 34 * pulse)), veil.get_rect(),
                     border_radius=10)
    surface.blit(veil, (x - 15, top))
    # pillars + lintel
    pygame.draw.rect(surface, sil, (x - 30, top, 12, base - top), border_radius=3)
    pygame.draw.rect(surface, sil, (x + 18, top, 12, base - top), border_radius=3)
    pygame.draw.rect(surface, sil, (x - 34, top - 12, 68, 14), border_radius=3)
    pygame.draw.line(surface, PALETTE["rim"], (x - 28, base - 4), (x - 20, top + 6), 2)
    _glow(surface, (x, (top + base) // 2), int(10 + pulse * 6), color, 90)
    _shadow(surface, (x, base), 30)


def draw_figure(surface: pygame.Surface, figure, face_states, to_screen,
                time: float) -> None:
    """The Three-Faced: a tall robed figure whose faces are doors to the levels.

    `face_states` matches `figure.faces`; "available" faces glow and open their
    eyes, "locked" faces keep their eyes shut and stay dim.
    """
    bx, by = to_screen(figure.x, figure.y, 0.0)
    sil = PALETTE["silhouette"]
    rim = PALETTE["rim"]

    # robe: a tall tapering column, hem at the ground
    top = by - 190
    pygame.draw.polygon(surface, sil, [
        (bx - 62, by), (bx + 62, by), (bx + 38, top + 30), (bx - 38, top + 30),
    ])
    pygame.draw.line(surface, rim, (bx - 56, by - 6), (bx - 34, top + 34), 2)
    pygame.draw.line(surface, rim, (bx + 40, top + 40), (bx + 50, by - 20), 1)
    # hood
    pygame.draw.circle(surface, sil, (bx, top + 14), 28)
    pygame.draw.circle(surface, rim, (bx, top + 14), 27, 1)
    _shadow(surface, (bx, by), 62)

    for face, state in zip(figure.faces, face_states):
        fx, fy = to_screen(face.x, face.y, 0.0)
        available = state == "available"
        color = PALETTE["spore"] if available else PALETTE["spore_dim"]
        pulse = 0.5 + 0.5 * math.sin(time * (1.8 if available else 0.5) + fx * 0.01)
        pygame.draw.circle(surface, sil, (fx, fy), 13)
        mask = [(fx + dx, fy + dy) for dx, dy in
                ((-8, -8), (5, -10), (11, -1), (6, 10), (-5, 10), (-10, 0))]
        pygame.draw.polygon(surface, PALETTE["bone"], mask)
        pygame.draw.polygon(surface, PALETTE["rim"], mask, 1)
        if available:
            eye = (fx, int(fy - 2))
            _glow(surface, eye, int(4 + pulse * 4), color, int(120 + 60 * pulse))
            pygame.draw.circle(surface, color, (fx - 3, eye[1]), 2)
            pygame.draw.circle(surface, color, (fx + 3, eye[1]), 2)
        else:
            pygame.draw.line(surface, PALETTE["flesh_dark"],
                             (fx - 5, fy - 2), (fx - 1, fy - 2), 2)
            pygame.draw.line(surface, PALETTE["flesh_dark"],
                             (fx + 1, fy - 2), (fx + 5, fy - 2), 2)

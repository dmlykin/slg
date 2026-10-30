"""Enemy AI state transitions: crawler melee loop, spitter ranged loop."""

from __future__ import annotations


from tests.conftest import run_frames


def _crawler(session):
    return session.enemies[0]


def _spitter(session):
    return session.enemies[1]


def test_crawler_patrols_within_range(session):
    run_frames(session, 3.0)
    c = _crawler(session)
    assert c.state == "patrol"
    assert abs(c.entity.x - c.spawn_x) <= c.c.patrol_range + 30


def test_crawler_aggros_when_player_close(session):
    run_frames(session, 0.5)
    c = _crawler(session)
    session.player.entity.x = c.entity.x + 150
    session.player.entity.y = c.entity.y
    run_frames(session, 0.2)
    assert c.state in ("aggro", "telegraph")


def test_crawler_full_attack_cycle(session):
    run_frames(session, 0.5)
    p = session.player
    c = _crawler(session)
    p.entity.x = c.entity.x + 55  # inside attack range
    p.entity.y = c.entity.y
    telegraphs = []
    session.bus.subscribe("telegraph", lambda entity, kind, duration: telegraphs.append(kind))

    # wait through aggro -> telegraph
    for _ in range(120):
        run_frames(session, 0.05)
        if c.state == "telegraph":
            break
    assert c.state == "telegraph"
    run_frames(session, c.c.telegraph + 0.01)
    assert c.state == "strike"
    run_frames(session, c.c.strike_active + 0.01)
    assert c.state == "recover"
    run_frames(session, c.c.recover + 0.01)
    assert c.state == "aggro"
    assert "crawler_bite" in telegraphs


def test_crawler_bite_damages_player(session):
    run_frames(session, 0.5)
    p = session.player
    c = _crawler(session)
    p.entity.x = c.entity.x + 40
    p.entity.y = c.entity.y
    hp0 = p.entity.hp
    # run until the crawler lands a strike (player stands still, takes it)
    for _ in range(200):
        run_frames(session, 0.05)
        if p.entity.hp < hp0:
            break
    assert p.entity.hp < hp0


def test_spitter_keeps_distance(session):
    run_frames(session, 0.5)
    p = session.player
    s = _spitter(session)
    p.entity.x = s.entity.x - 100  # too close -> should hop away
    p.entity.y = s.entity.y
    run_frames(session, 0.3)
    assert s.state == "aggro"
    assert s.entity.x > s.spawn_x  # moved away from the player


def test_spitter_spits_projectile(session):
    run_frames(session, 0.5)
    p = session.player
    s = _spitter(session)
    p.entity.x = s.entity.x - 300  # inside the keep band
    p.entity.y = s.entity.y
    for _ in range(200):
        run_frames(session, 0.05)
        if s.state == "telegraph":
            break
    assert s.state == "telegraph"
    run_frames(session, s.s.telegraph + 0.01)
    assert s.state == "recover"
    assert len(session.projectiles) == 1


def test_projectile_hits_player_or_expires(session):
    run_frames(session, 0.5)
    p = session.player
    s = _spitter(session)
    p.entity.x = s.entity.x - 250
    p.entity.y = s.entity.y
    hp0 = p.entity.hp
    hit = False
    for _ in range(400):
        run_frames(session, 0.05)
        if p.entity.hp < hp0:
            hit = True
            break
    assert hit or session.projectiles == [] or p.entity.hp < hp0


def test_dead_player_ignored_by_enemies(session):
    run_frames(session, 0.5)
    p = session.player
    p.entity.hp = 1
    p.take_hit(10, 0.0)
    assert p.state == "dead"
    c = _crawler(session)
    run_frames(session, 1.0)
    assert c.state == "patrol"

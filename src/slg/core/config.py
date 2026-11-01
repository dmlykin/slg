"""All gameplay timings and numbers live here — tune the feel without touching logic."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class PhysicsConfig:
    gravity: float = 2400.0          # px/s^2
    max_fall_speed: float = 1400.0   # px/s
    fixed_dt: float = 1.0 / 60.0     # simulation step


@dataclass(frozen=True)
class PlayerConfig:
    max_hp: int = 100
    max_stamina: float = 100.0
    stamina_regen: float = 34.0        # per second, when not spending
    stamina_regen_delay: float = 0.45  # seconds after an action before regen
    run_speed: float = 270.0
    accel: float = 2600.0
    air_control: float = 0.55
    jump_velocity: float = -840.0
    jump_cut_multiplier: float = 0.45  # velocity kept when Space released early
    coyote_time: float = 0.10
    heal_charges: int = 3
    heal_amount: int = 45
    hurt_stun: float = 0.28
    hurt_knockback: float = 260.0
    invuln_after_hit: float = 0.35
    width: float = 26.0
    height: float = 56.0


@dataclass(frozen=True)
class RollConfig:
    duration: float = 0.38
    speed: float = 540.0
    stamina_cost: float = 26.0
    iframes_start: float = 0.03
    iframes_end: float = 0.30


@dataclass(frozen=True)
class AttackConfig:
    """A weapon swing: windup -> active (hitbox live) -> recovery."""

    name: str
    windup: float
    active: float
    recovery: float
    damage: int
    stamina_cost: float
    stagger_damage: float
    reach: float          # hitbox horizontal extent from entity center
    height: float         # hitbox vertical extent
    knockback: float = 180.0
    hit_pause: float = 0.05


@dataclass(frozen=True)
class CombatConfig:
    light: AttackConfig = field(
        default_factory=lambda: AttackConfig(
            name="light",
            windup=0.13, active=0.08, recovery=0.21,
            damage=12, stamina_cost=14.0, stagger_damage=22.0,
            reach=64.0, height=46.0, knockback=170.0,
        )
    )
    heavy: AttackConfig = field(
        default_factory=lambda: AttackConfig(
            name="heavy",
            windup=0.34, active=0.10, recovery=0.40,
            damage=30, stamina_cost=32.0, stagger_damage=48.0,
            reach=78.0, height=54.0, knockback=340.0,
        )
    )
    heal_duration: float = 0.95


@dataclass(frozen=True)
class CrawlerConfig:
    """Melee enemy: patrol -> aggro -> telegraph -> strike -> recover."""

    max_hp: int = 42
    patrol_speed: float = 60.0
    chase_speed: float = 175.0
    patrol_range: float = 110.0
    aggro_range: float = 300.0
    aggro_vertical: float = 90.0
    attack_range: float = 62.0
    telegraph: float = 0.48
    strike_active: float = 0.12
    recover: float = 0.85
    damage: int = 14
    knockback: float = 300.0
    stagger_damage: float = 18.0
    poise: float = 40.0
    poise_regen: float = 20.0
    stagger_time: float = 0.9
    width: float = 46.0
    height: float = 30.0


@dataclass(frozen=True)
class SpitterConfig:
    """Ranged enemy: keeps distance, telegraphs, lobs a spore projectile."""

    max_hp: int = 30
    hop_speed: float = 240.0
    keep_min: float = 170.0
    keep_max: float = 420.0
    aggro_range: float = 460.0
    telegraph: float = 0.62
    recover: float = 1.25
    projectile_speed: float = 460.0
    projectile_arc: float = -320.0   # initial vertical velocity (upward)
    projectile_damage: int = 12
    projectile_radius: float = 9.0
    poise: float = 25.0
    poise_regen: float = 20.0
    stagger_time: float = 0.8
    width: float = 38.0
    height: float = 40.0


@dataclass(frozen=True)
class ShardConfig:
    """Ambush enemy: dormant shard -> glint -> dash through the player -> recover."""

    max_hp: int = 34
    wake_radius: float = 150.0
    wake_vertical: float = 110.0
    telegraph: float = 0.5
    lunge_time: float = 0.3
    lunge_speed: float = 620.0
    lunge_damage: int = 16
    lunge_knockback: float = 340.0
    recover: float = 1.4
    drift_speed: float = 55.0
    relunge_cooldown: float = 1.1
    poise: float = 30.0
    poise_regen: float = 20.0
    stagger_time: float = 0.7
    width: float = 34.0
    height: float = 44.0


@dataclass(frozen=True)
class OrbConfig:
    """Ball lightning of the well: an invulnerable floating hazard.

    It hovers above its ledge, homes in on the player and hurts on contact.
    Lure it over the central shaft and it falls; the boss arena floor shatters
    it on impact.
    """

    width: float = 34.0
    height: float = 34.0
    float_speed: float = 110.0
    chase_speed: float = 170.0
    aggro_range: float = 340.0
    aggro_vertical: float = 140.0
    hover_lift: float = 16.0
    bob_amplitude: float = 5.0
    bob_rate: float = 3.2
    contact_damage: int = 14
    contact_knockback: float = 280.0
    contact_cooldown: float = 0.9


@dataclass(frozen=True)
class BossConfig:
    max_hp: int = 420
    move_speed: float = 150.0
    phase2_at: float = 0.5           # fraction of max_hp
    phase2_speed_mult: float = 1.35
    phase2_telegraph_mult: float = 0.7
    poise: float = 120.0
    poise_regen: float = 30.0
    stagger_time: float = 1.1
    width: float = 96.0
    height: float = 120.0
    # patterns
    slam_telegraph: float = 0.70
    slam_active: float = 0.16
    slam_recover: float = 0.90
    slam_damage: int = 26
    slam_range: float = 150.0
    sweep_telegraph: float = 0.62
    sweep_active: float = 0.14
    sweep_recover: float = 0.75
    sweep_damage: int = 18
    sweep_range: float = 190.0
    volley_telegraph: float = 0.66
    volley_recover: float = 1.05
    volley_count: int = 5
    volley_spread: float = 0.36
    volley_damage: int = 10
    volley_projectile_speed: float = 380.0
    idle_between_patterns: float = 0.55
    # distance band kept during idle (0 = close in like the level 01 boss)
    keep_min: float = 0.0
    keep_max: float = 0.0


@dataclass(frozen=True)
class KeeperConfig(BossConfig):
    """Blind keeper of the well: hears noise, strikes where it last heard you."""

    max_hp: int = 480
    move_speed: float = 120.0
    phase2_at: float = 0.5
    phase2_speed_mult: float = 1.25
    phase2_telegraph_mult: float = 0.78
    poise: float = 120.0
    poise_regen: float = 28.0
    stagger_time: float = 1.0
    width: float = 76.0
    height: float = 136.0
    # lantern slam
    slam_telegraph: float = 0.75
    slam_active: float = 0.24
    slam_recover: float = 1.00
    slam_damage: int = 26
    slam_range: float = 170.0
    # echo wave
    sweep_telegraph: float = 0.65
    sweep_active: float = 1.0
    sweep_recover: float = 0.90
    sweep_damage: int = 18
    sweep_range: float = 800.0
    # call of the deep (falling orbs + shock zones)
    volley_telegraph: float = 0.80
    volley_recover: float = 1.00
    volley_count: int = 2
    volley_damage: int = 14
    idle_between_patterns: float = 0.90
    # hearing
    hearing_memory: float = 2.5
    echo_speed: float = 850.0
    echo_thickness: float = 40.0
    orb_fall_time: float = 0.45
    orb_fall_height: float = 380.0
    orb_spread: float = 120.0
    orb_zone_radius: float = 70.0
    orb_zone_life: float = 1.6
    zone_hit_cooldown: float = 0.70
    keep_min: float = 0.0
    keep_max: float = 0.0


@dataclass(frozen=True)
class HubConfig:
    """Hub interactions: the Three-Faced figure and its faces."""

    face_radius: float = 70.0      # horizontal reach of one face's zone


@dataclass(frozen=True)
class Config:
    """Root config. Replace via dataclasses.replace for tuning."""

    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    player: PlayerConfig = field(default_factory=PlayerConfig)
    roll: RollConfig = field(default_factory=RollConfig)
    combat: CombatConfig = field(default_factory=CombatConfig)
    crawler: CrawlerConfig = field(default_factory=CrawlerConfig)
    spitter: SpitterConfig = field(default_factory=SpitterConfig)
    shard: ShardConfig = field(default_factory=ShardConfig)
    orb: OrbConfig = field(default_factory=OrbConfig)
    boss: BossConfig = field(default_factory=BossConfig)
    blade: BossConfig = field(default_factory=lambda: BossConfig(
        max_hp=260,
        move_speed=190.0,
        poise=90.0,
        poise_regen=26.0,
        width=64.0,
        height=96.0,
        slam_telegraph=0.50,
        slam_active=0.14,
        slam_recover=0.62,
        slam_damage=22,
        slam_range=140.0,
        sweep_telegraph=0.42,
        sweep_active=0.12,
        sweep_recover=0.52,
        sweep_damage=16,
        sweep_range=180.0,
        volley_count=3,
        volley_damage=9,
        idle_between_patterns=0.32,
    ))
    prism: BossConfig = field(default_factory=lambda: BossConfig(
        max_hp=170,
        move_speed=165.0,
        poise=70.0,
        poise_regen=24.0,
        width=64.0,
        height=96.0,
        slam_telegraph=0.60,
        slam_active=0.14,
        slam_recover=0.80,
        slam_damage=18,
        slam_range=130.0,
        sweep_telegraph=0.55,
        sweep_active=0.12,
        sweep_recover=0.70,
        sweep_damage=13,
        sweep_range=170.0,
        volley_telegraph=0.55,
        volley_recover=0.78,
        volley_count=6,
        volley_spread=0.40,
        volley_damage=9,
        volley_projectile_speed=430.0,
        idle_between_patterns=0.50,
        keep_min=250.0,
        keep_max=470.0,
    ))
    keeper: KeeperConfig = field(default_factory=KeeperConfig)
    hub: HubConfig = field(default_factory=HubConfig)

    def with_overrides(self, **section_overrides) -> Config:
        cfg = self
        for name, overrides in section_overrides.items():
            section = getattr(cfg, name)
            cfg = replace(cfg, **{name: replace(section, **overrides)})
        return cfg

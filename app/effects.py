from pedalboard import (
    Reverb, Delay, Gain, Chorus, Distortion,
    Compressor, LowpassFilter, HighpassFilter, Phaser,
)

# Each effect maps to its Pedalboard class plus a parameter definition
# The parameters drives the UI knobs & bound check for every render request
EFFECT_REGISTRY = {
    "Gain": {
        "cls": Gain,
        "params": {
            "gain_db": {"min": -60, "max": 24, "default": 0, "step": 0.5},
        },
    },
    "Reverb": {
        "cls": Reverb,
        "params": {
            "room_size": {"min": 0, "max": 1, "default": 0.5, "step": 0.01},
            "damping":   {"min": 0, "max": 1, "default": 0.5, "step": 0.01},
            "wet_level": {"min": 0, "max": 1, "default": 0.33, "step": 0.01},
            "dry_level": {"min": 0, "max": 1, "default": 0.4, "step": 0.01},
            "width":     {"min": 0, "max": 1, "default": 1.0, "step": 0.01},
        },
    },
    "Delay": {
        "cls": Delay,
        "params": {
            "delay_seconds": {"min": 0, "max": 2.0, "default": 0.5, "step": 0.01},
            "feedback":      {"min": 0, "max": 1, "default": 0.3, "step": 0.01},
            "mix":           {"min": 0, "max": 1, "default": 0.5, "step": 0.01},
        },
    },
    "Chorus": {
        "cls": Chorus,
        "params": {
            "rate_hz":         {"min": 0, "max": 100, "default": 1.0, "step": 0.1},
            "depth":           {"min": 0, "max": 1, "default": 0.25, "step": 0.01},
            "centre_delay_ms": {"min": 1, "max": 50, "default": 7.0, "step": 0.1},
            "feedback":        {"min": 0, "max": 1, "default": 0.0, "step": 0.01},
            "mix":             {"min": 0, "max": 1, "default": 0.5, "step": 0.01},
        },
    },
    "Distortion": {
        "cls": Distortion,
        "params": {
            "drive_db": {"min": 0, "max": 60, "default": 25, "step": 0.5},
        },
    },
    "Compressor": {
        "cls": Compressor,
        "params": {
            "threshold_db": {"min": -60, "max": 0, "default": -16, "step": 0.5},
            "ratio":        {"min": 1, "max": 20, "default": 4, "step": 0.1},
            "attack_ms":    {"min": 0.1, "max": 100, "default": 1.0, "step": 0.1},
            "release_ms":   {"min": 10, "max": 1000, "default": 100, "step": 1},
        },
    },
    "LowpassFilter": {
        "cls": LowpassFilter,
        "params": {
            "cutoff_frequency_hz":
                {"min": 20, "max": 20000, "default": 2000, "step": 10},
        },
    },
    "HighpassFilter": {
        "cls": HighpassFilter,
        "params": {
            "cutoff_frequency_hz":
                {"min": 20, "max": 20000, "default": 200, "step": 10},
        },
    },
    "Phaser": {
        "cls": Phaser,
        "params": {
            "rate_hz":  {"min": 0, "max": 20, "default": 1.0, "step": 0.1},
            "depth":    {"min": 0, "max": 1, "default": 0.5, "step": 0.01},
            "feedback": {"min": 0, "max": 1, "default": 0.0, "step": 0.01},
            "mix":      {"min": 0, "max": 1, "default": 0.5, "step": 0.01},
        },
    },
}

def schema_for_ui():
    """JSON copy for the browser. Does not send python object"""
    return {name: spec["params"] for name, spec in EFFECT_REGISTRY.items()}
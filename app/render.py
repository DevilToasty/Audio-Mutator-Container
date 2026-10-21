from pedalboard import Pedalboard # import dependencies
from pedalboard.io import AudioFile
from app.effects import EFFECT_REGISTRY # from our program

def build_board(chain: list[dict]) -> Pedalboard:
    # Turns a chain of {effect_type, parameters} into a Pedalboard per documentation
    # Rejects unknown effects and param, and clamps values to bounds
    plugins = []
    for node in chain:
        etype = node.get("effect_type")
        if etype not in EFFECT_REGISTRY:
            raise ValueError(f"Unknown effect: {etype}")
        spec = EFFECT_REGISTRY[etype]
        kwargs = {}
        for pname, pval in (node.get("parameters") or {}).items():
            if pname not in spec["params"]:
                raise ValueError(f"Unknown param {pname} for {etype}")
            p = spec["params"][pname]
            # clamp [min, max]
            kwargs[pname] = max(p["min"], min(p["max"], float(pval)))
        plugins.append(spec["cls"](**kwargs))
    return Pedalboard(plugins)

def render(original_path: str, rendered_path: str, chain: list[dict]) -> None:
    # Read the orignal, process through the chain, write the rendered cache
    board = build_board(chain)
    with AudioFile(original_path) as f:
        audio = f.read(f.frames)
        samplerate = f.samplerate
    processed = board(audio, samplerate)
    with AudioFile(rendered_path, "w", samplerate, processed.shape[0]) as f:
        f.write(processed) # audio file output
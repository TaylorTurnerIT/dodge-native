"""Fixed observation-only unit policy copied from pinned native binding controls."""
import numpy as np

def avoidance_actions(observations):
    # Fixed observation-only unit fixture. No policy search, training, RNG or
    # seed replacement. Twelve-frame linear prediction is not an evaluator.
    actions = []
    directions = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (1, -1), (-1, 1), (1, 1)]
    for g, entities, types, mask in zip(observations["global_feats"][:, 0],
                                      observations["entity_feats"],
                                      observations["entity_types"],
                                      observations["entity_mask"]):
        enemies = entities[mask & (types >= 1) & (types <= 3)]
        best = None
        for action, (ax, ay) in enumerate(directions):
            x, y = float(g[0])*64+64, float(g[1])*64+64
            vx, vy = float(g[2])*2.5, float(g[3])*2.5
            clearance = 12.0
            for frame in range(1, 13):
                vx, vy = vx*0.8+ax*0.5, vy*0.8+ay*0.5
                x, y = min(125, max(2, x+vx)), min(125, max(2, y+vy))
                if len(enemies):
                    ex = enemies[:, 0]*128+64+enemies[:, 6]*4*frame
                    ey = enemies[:, 1]*128+64+enemies[:, 7]*4*frame
                    hx = enemies[:, 2]*64+float(g[4])*4-1
                    hy = enemies[:, 3]*64+float(g[4])*4-1
                    clearance = min(clearance, float(np.minimum(
                        np.maximum(np.abs(x-ex)-hx, np.abs(y-ey)-hy), 12).min()))
            score = clearance - 0.002*((x-64)**2+(y-64)**2)**0.5
            candidate = (score, -action, action)
            if best is None or candidate > best:
                best = candidate
        actions.append(best[2])
    return actions

"""Context-aware stochastic policy. Outcome calibration and tactical rules are separate."""
import math
from .model import Model

MODEL = Model()

def candidates(sim):
    p = sim.players[sim.owner]; team = p['team']
    x = sim.progress(p['x'], team)
    opponents = [i for i,q in enumerate(sim.players) if q['active'] and q['team']!=team]
    nearest = min(math.hypot(sim.players[i]['x']-p['x'],sim.players[i]['y']-p['y']) for i in opponents)
    pressured = nearest < 3
    weights = MODEL.action_weights(x)
    options = []
    defenders = sorted((sim.progress(sim.players[i]['x'], team) for i in opponents),reverse=True)
    offside = max(x, defenders[1] if len(defenders)>1 else 105, 52.5)
    for i,q in enumerate(sim.players):
        if i==sim.owner or not q['active'] or q['team']!=team:
            continue
        qx = sim.progress(q['x'],team)
        if qx>offside+.15:
            continue
        dx,dy=q['x']-p['x'],q['y']-p['y']; length=math.hypot(dx,dy)
        if length<2 or length>48:
            continue
        # Locate the most dangerous defender along the segment, excluding the passer's feet.
        risks=[]
        for j in opponents:
            o=sim.players[j]
            u=max(.08,min(1,((o['x']-p['x'])*dx+(o['y']-p['y'])*dy)/max(length*length,1e-9)))
            lateral=math.hypot(o['x']-p['x']-u*dx,o['y']-p['y']-u*dy)
            margin=.3+max(0,lateral-1)/7.2-u*length/14
            risks.append((margin,j))
        margin, defender=min(risks)
        success=max(.08,min(.98,MODEL.pass_success(length,pressured)))
        advance=qx-x
        geometry=MODEL.profile.get('pass_geometry',{}).get(str(min(3,int(x//26.25))),{})
        lengths=geometry.get('lengths',[.2]*5)
        weight=lengths[min(4,int(length//10))]*math.exp(-max(0,-margin)*.8)*success**2
        if x>88 and advance < -30 and nearest>4:
            weight*=.025
        options.append({'kind':'pass','recipient':i,'defender':defender,'distance':length,
                        'success':success,'weight':weights['pass']*weight,'advance':advance,'pressured':pressured})
    geometry=MODEL.profile.get('pass_geometry',{}).get(str(min(3,int(x//26.25))),{})
    backward=geometry.get('backward',.4)
    for backwards, mass in ((True,backward),(False,1-backward)):
        group=[o for o in options if (o['advance'] < -1)==backwards]
        group_total=sum(o['weight'] for o in group)
        if group_total:
            for o in group: o['weight']=o['weight']/group_total*mass
    total=sum(o['weight'] for o in options)
    if total:
        for o in options: o['weight']=o['weight']/total*weights['pass']
    for o in options:
        if x>88 and o['advance'] < -30 and nearest>4: o['weight']*=.025
    if p['number']!=1:
        distance=math.hypot(105-x,p['y']-34)
        angle=abs(math.atan2(3.66-(p['y']-34),max(.1,105-x))-math.atan2(-3.66-(p['y']-34),max(.1,105-x)))
        if distance<32 and angle>.12:
            goal=MODEL.shot_goal(x,p['y'])
            options.append({'kind':'shot','weight':weights['shot']*max(.25,min(5,goal/.10))*(.7 if pressured else 1.3),'goal_probability':goal})
        options.append({'kind':'carry','weight':weights['carry']*(.5 if pressured else 1.),'pressured':pressured})
    if not options:
        options=[{'kind':'carry','weight':1.,'pressured':pressured}]
    if sim.attribute_actions:
        from .player_actions import adjust_options
        return adjust_options(options, p, sim.action_multipliers, sim.attribute_strength)
    return options

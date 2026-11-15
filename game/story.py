"""Player-facing narrative for Cannon: Eight Days Left.

Every line is ``(speaker, text)``.  ``{name}`` is replaced at runtime.
The script deliberately keeps exposition short and ties every puzzle to the
people threatened by the Foreman's route.
"""

SPEAKERS = {
    "VEGA": {"portrait": "portrait_vega", "color": (0.55, 0.85, 1.00)},
    "TOKO": {"portrait": "portrait_toko", "color": (1.00, 0.70, 0.28)},
    "MARA": {"portrait": "portrait_mara", "color": (0.55, 1.00, 0.82)},
    "WARDEN": {"portrait": "portrait_warden", "color": (1.00, 0.35, 0.35)},
    "FOREMAN": {"portrait": "portrait_foreman", "color": (1.00, 0.55, 0.20)},
}


def fmt(text, name):
    return text.replace("{name}", name)


ENLISTMENT = [
    ("VEGA", "PV-1 enlistment terminal. This is Commander Vega."),
    ("VEGA", "I have one cannon and eight days. Tell me your name."),
]


# Five panels, ten spoken lines in total.
INTRO = [
    ("intro_outpost", [
        ("MARA", "PV-1, this is Meridian Shelter Two. Mining rigs are moving toward us. Families are going below the refinery."),
        ("VEGA", "That is my sister, Mara. Meridian is one of three colonies in the machines' path."),
    ]),
    ("intro_derelicts", [
        ("VEGA", "The Guild abandoned a mining fleet in this belt. Three weeks ago its command unit woke up."),
        ("FOREMAN", "WORK ORDER ACTIVE. STRIP THE BELT. SHIP ALL MATERIAL."),
    ]),
    ("intro_awakening", [
        ("VEGA", "The Foreman is building a jump route for that fleet. It reaches the colonies in eight days."),
        ("MARA", "We cannot move two hundred thousand people in time."),
    ]),
    ("intro_beacons", [
        ("VEGA", "Ten signal beacons hold the route together. It can recalculate while even one remains."),
        ("TOKO", "I brought the last working cannon online. It still needs a gunner."),
    ]),
    ("intro_turret", [
        ("VEGA", "Destroy all ten beacons before the fleet reaches Meridian, Halde and New Sun."),
        ("TOKO", "Take the controls, {name}. I will keep the old gun breathing."),
    ]),
]


# Two lines per level: one human stake, followed by one useful instruction.
BRIEFINGS = {
    0: [
        ("VEGA", "Beacon one is pointing the fleet at Meridian, where Mara is waiting below ground."),
        ("TOKO", "Aim with the mouse, set power with the wheel, then press Space to fire."),
    ],
    1: [
        ("MARA", "The machines reached our outer pumps. We can hear the drills through the shelter wall."),
        ("TOKO", "Break the rubble with bullets or arc over it. Both routes are open."),
    ],
    2: [
        ("VEGA", "That wall protects the next route lock. Meridian loses another escape lane if it stays active."),
        ("TOKO", "Select the Bombshell with 2. Drill a breach, then fire through the opening."),
    ],
    3: [
        ("MARA", "Our lights just failed. The shelter has six hours of reserve power."),
        ("TOKO", "Perpetio cannot be damaged. Raise the barrel and drop a shell over the top."),
    ],
    4: [
        ("VEGA", "The Mirror Warden guards the fifth beacon. Break it and Meridian gets a clear evacuation corridor."),
        ("TOKO", "Select the Laser with 3. Use the mirror arrays to bend the beam around the shield."),
    ],
    5: [
        ("VEGA", "Halde reports mining rigs at its water plant. This beacon is guiding them in."),
        ("TOKO", "There is one clean window through the plate. Keep the trajectory inside it."),
    ],
    6: [
        ("MARA", "Halde is moving children into the ice tunnels. Keep that route away from them."),
        ("TOKO", "A shot keeps its speed through a wormhole. Aim from the exit toward the beacon."),
    ],
    7: [
        ("VEGA", "New Sun has no shelters. Its farms and homes are open to the surface."),
        ("TOKO", "The blue anomaly pulls massive shells. Let its gravity curve your shot past the wall."),
    ],
    8: [
        ("MARA", "New Sun is sending families into freight tunnels. They need this beacon dark."),
        ("TOKO", "Bounce a massive shell from the pink elastonio pane to reach under the roof."),
    ],
    9: [
        ("VEGA", "Nine beacons are dark. The Foreman is rebuilding the route from its own core."),
        ("TOKO", "Use every path we learned. The first phase needs the wormhole and elastonio pane."),
    ],
}


# One concrete consequence after each completed level.
VICTORIES = {
    0: [("VEGA", "Beacon one is dark. The rigs outside Meridian changed course.")],
    1: [("MARA", "The drilling stopped for a moment. People here heard it stop.")],
    2: [("TOKO", "The breach is open and the third route lock is gone.")],
    3: [("MARA", "Power crews reached our shelter while the rigs were diverted.")],
    4: [("VEGA", "The Warden is down. Meridian's evacuation corridor is clear.")],
    5: [("VEGA", "Halde's water plant is no longer on the fleet route.")],
    6: [("MARA", "Halde confirms that the children reached the ice tunnels.")],
    7: [("VEGA", "The fleet turned away from New Sun's surface farms.")],
    8: [("MARA", "New Sun's freight tunnels are clear. Only the Foreman remains.")],
    9: [("FOREMAN", "ROUTE INCOMPLETE. FLEET COMMAND SUSPENDED.")],
}


# Short consequence scenes after levels 3, 6 and 9.  Art is optional.
INTERLUDES = {
    2: [("interlude_meridian", [
        ("MARA", "The rigs have turned away from the refinery road. We're using the gap to move families deeper underground."),
        ("VEGA", "It is only a delay. Halde is next on the route."),
    ])],
    5: [("interlude_halde", [
        ("VEGA", "Halde opened its water plant again. The colony has a working evacuation lane."),
        ("MARA", "New Sun is still exposed. Finish the route before the fleet turns there."),
    ])],
    8: [("interlude_new_sun", [
        ("MARA", "New Sun's families reached the freight tunnels. The sky is clear for now."),
        ("VEGA", "The Foreman is rebuilding from its core. One beacon left."),
    ])],
}


PHASE_DIALOGUE = {
    (4, 1): [
        ("WARDEN", "ARRAY GEOMETRY RECALCULATED."),
        ("TOKO", "The mirrors moved. Trace the new angle and hit the Warden again."),
    ],
    (9, 1): [
        ("FOREMAN", "CORE DAMAGE LOGGED. ROUTE REPAIR IN PROGRESS."),
        ("VEGA", "The new gate ends beside mirror glass. Send the laser through and reflect it into the core."),
    ],
    (9, 2): [
        ("FOREMAN", "FINAL SHIPPING PATH LOCKED."),
        ("TOKO", "Use a bullet. Send it through the upper channel and let the Gravitonio pull it under the last shield."),
    ],
}


EPILOGUE = [
    ("epilogue_dawn", [
        ("MARA", "The machines outside our shelter stopped. I can hear people opening the doors."),
        ("VEGA", "All ten beacons are dark. Meridian, Halde and New Sun are safe."),
        ("TOKO", "The cannon held together, {name}. I put your name beside its builders."),
        ("VEGA", "Come home, Commander {name}. Your watch is over."),
    ]),
]


# Headings are documentation metadata. Spoken text is read from the structures
# above, so render_markdown() follows the script used by the game.
LEVEL_TITLES = (
    "Training Range", "The Rubble Line", "Dig Deep",
    "The Perpetio Shield", "Light Bends", "Mirror Canyon",
    "The Wormhole Run", "Gravity Well", "Repulsor Ridge",
    "The Gauntlet",
)
INTERLUDE_TITLES = {
    2: "Meridian interlude",
    5: "Halde interlude",
    8: "New Sun interlude",
}


def _markdown_lines(lines):
    """Render one ordered group of spoken lines."""
    result = []
    for speaker, text in lines:
        result.extend((f"**{speaker}:** {text}", ""))
    return result


def render_markdown():
    """Return the canonical readable script.

    The renderer walks the same containers used at runtime. File comparison
    can therefore detect missing, extra, duplicate, stale or reordered lines.
    """
    output = [
        "# Cannon: Eight Days Left", "",
        "This is the canonical readable copy of the player-facing script in",
        "`game/story.py`. Regenerate it with `python3 game/story.py`.", "",
        "## Enlistment", "",
    ]
    output.extend(_markdown_lines(ENLISTMENT))
    output.extend(("## Introduction", ""))
    for image_name, lines in INTRO:
        title = image_name.removeprefix("intro_").replace("_", " ").title()
        output.extend((f"### {title}", ""))
        output.extend(_markdown_lines(lines))

    output.extend(("## Level briefings and victories", ""))
    for index, title in enumerate(LEVEL_TITLES):
        output.extend((f"### Level {index + 1}: {title}", ""))
        output.extend(_markdown_lines(BRIEFINGS[index]))
        for phase in range(1, 4):
            output.extend(_markdown_lines(PHASE_DIALOGUE.get((index, phase), ())))
        output.extend(_markdown_lines(VICTORIES[index]))
        if index in INTERLUDES:
            output.extend((f"### {INTERLUDE_TITLES[index]}", ""))
            for _image_name, lines in INTERLUDES[index]:
                output.extend(_markdown_lines(lines))

    output.extend(("## Epilogue", ""))
    for _image_name, lines in EPILOGUE:
        output.extend(_markdown_lines(lines))
    return "\n".join(output).rstrip() + "\n"


def write_markdown(path=None):
    """Write the canonical script beside this module's package."""
    if path is None:
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "STORY.md")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_markdown())


if __name__ == "__main__":
    write_markdown()

"""Realistic mechanical parts modelled in CadQuery.

Each :class:`PartSpec` builds exactly one closed solid with dimensions in the
10-200 mm range, the sort of geometry a maker or mechanical engineer would
actually export to STL.  The library is the ground truth for the mesh-to-STEP
reconstruction benchmark, so every build must be deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class PartSpec:
    """One benchmark part: a slug, human title, feature tags and a builder."""

    slug: str
    title: str
    tags: tuple[str, ...]
    build: Callable[[], cq.Workplane]
    units: str = "mm"
    notes: str = ""


# --------------------------------------------------------------------------
# 01 - L bracket with gusset
# --------------------------------------------------------------------------
def _build_l_bracket_gusset() -> cq.Workplane:
    base = cq.Workplane("XY").box(70, 50, 8, centered=(True, True, False))
    base = base.edges("|Z and >X").fillet(8)
    wall = cq.Workplane("XY").box(8, 50, 55, centered=(True, True, False)).translate((-31, 0, 0))
    gusset = (
        cq.Workplane("XZ").moveTo(-27, 8).lineTo(-27, 46).lineTo(2, 8).close().extrude(4, both=True)
    )
    body = base.union(wall).union(gusset)
    body = body.edges(">Z and |Y").chamfer(1.5)
    base_holes = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .pushPoints([(12.0, 16.0), (12.0, -16.0), (28.0, 0.0)])
        .circle(3.4)
        .extrude(10)
    )
    wall_holes = (
        cq.Workplane("YZ")
        .workplane(offset=-40)
        .pushPoints([(16.0, 24.0), (-16.0, 24.0), (16.0, 40.0), (-16.0, 40.0)])
        .circle(2.6)
        .extrude(20)
    )
    return body.cut(base_holes).cut(wall_holes)


# --------------------------------------------------------------------------
# 02 - Four bolt pipe flange
# --------------------------------------------------------------------------
def _build_flange_four_bolt() -> cq.Workplane:
    body = (
        cq.Workplane("XZ")
        .moveTo(16, 0)
        .lineTo(55, 0)
        .lineTo(55, 10)
        .lineTo(28, 10)
        .lineTo(28, 34)
        .lineTo(16, 34)
        .close()
        .revolve()
    )
    body = body.faces(">Z").edges().fillet(2.0)
    body = body.edges("%CIRCLE and <Z").chamfer(1.0)
    return (
        body.faces("<Z")
        .workplane(centerOption="CenterOfBoundBox")
        .polarArray(42, 45, 360, 4)
        .cboreHole(9.0, 15.0, 6.0)
    )


# --------------------------------------------------------------------------
# 03 - NEMA 17 stepper motor mount
# --------------------------------------------------------------------------
def _build_motor_mount_nema17() -> cq.Workplane:
    plate = cq.Workplane("XY").box(60, 60, 6, centered=(True, True, False))
    plate = plate.edges("|Z").fillet(6)
    wall = cq.Workplane("XY").box(60, 8, 42, centered=(True, True, False)).translate((0, -26, 0))
    wall = wall.edges("|Z").fillet(3)
    body = plate.union(wall)
    body = body.faces(">Z").workplane().circle(11.5).cutThruAll()
    body = (
        body.faces(">Z")
        .workplane(centerOption="CenterOfBoundBox")
        .rarray(31, 31, 2, 2)
        .circle(1.7)
        .cutThruAll()
    )
    pocket = (
        cq.Workplane("XY").workplane(offset=-0.1).rect(44, 34).extrude(2.6).translate((0, 8, 0))
    )
    body = body.cut(pocket)
    slots = (
        cq.Workplane("XZ")
        .workplane(offset=40)
        .pushPoints([(-18.0, 24.0), (18.0, 24.0)])
        .slot2D(18, 6, 90)
        .extrude(80)
    )
    body = body.cut(slots)
    return body.edges(">Z and |X").chamfer(1.0)


# --------------------------------------------------------------------------
# 04 - 608 bearing pillow block
# --------------------------------------------------------------------------
def _build_bearing_block_608() -> cq.Workplane:
    body = cq.Workplane("XY").box(64, 26, 40, centered=(True, True, False))
    body = body.edges("|Y and >Z").fillet(9)
    bore = cq.Workplane("XY").workplane(offset=28).circle(11).extrude(20, both=True)
    body = body.cut(bore.translate((0, 0, 0)))
    counter = cq.Workplane("XZ").workplane(offset=-13.1).center(0, 28).circle(15).extrude(3.5)
    body = body.cut(counter).cut(counter.translate((0, 26.1, 0)))
    feet = cq.Workplane("XY").workplane(offset=-1).rarray(48, 1, 2, 1).circle(3.3).extrude(12)
    body = body.cut(feet)
    grub = cq.Workplane("XY").workplane(offset=36).circle(2.1).extrude(10)
    body = body.cut(grub)
    oiler = cq.Workplane("XY").workplane(offset=40).circle(3.0).extrude(-6).translate((22, 0, 0))
    return body.cut(oiler)


# --------------------------------------------------------------------------
# 05 - Hex standoff spacer
# --------------------------------------------------------------------------
def _build_hex_standoff() -> cq.Workplane:
    body = cq.Workplane("XY").polygon(6, 15.0).extrude(35)
    body = body.edges(">Z or <Z").chamfer(1.2)
    return body.faces(">Z").workplane().circle(2.6).cutThruAll()


# --------------------------------------------------------------------------
# 06 - Stepped shaft spacer
# --------------------------------------------------------------------------
def _build_stepped_shaft_spacer() -> cq.Workplane:
    body = (
        cq.Workplane("XZ")
        .moveTo(5, 0)
        .lineTo(22, 0)
        .lineTo(22, 9)
        .lineTo(14, 9)
        .lineTo(14, 30)
        .lineTo(10, 30)
        .lineTo(10, 46)
        .lineTo(5, 46)
        .close()
        .revolve()
    )
    return body.edges("%CIRCLE and (>Z or <Z)").chamfer(0.8)


# --------------------------------------------------------------------------
# 07 - V belt pulley
# --------------------------------------------------------------------------
def _build_v_belt_pulley() -> cq.Workplane:
    body = (
        cq.Workplane("XZ")
        .moveTo(8, 0)
        .lineTo(38, 0)
        .lineTo(38, 6)
        .lineTo(30, 12)
        .lineTo(38, 18)
        .lineTo(38, 24)
        .lineTo(8, 24)
        .close()
        .revolve()
    )
    body = body.faces(">Z").workplane().circle(6).cutThruAll()
    # Cut the keyway before the radial grub hole: OCCT builds an invalid shell
    # for the reverse order.
    keyway = cq.Workplane("XY").box(4, 4.4, 26, centered=(True, False, False)).translate((0, 4, -1))
    body = body.cut(keyway)
    grub = cq.Workplane("YZ").workplane(offset=-40).center(0, 4).circle(2.1).extrude(32)
    return body.cut(grub)


# --------------------------------------------------------------------------
# 08 - Fluted control knob
# --------------------------------------------------------------------------
def _build_fluted_knob() -> cq.Workplane:
    body = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(21, 0)
        .lineTo(21, 16)
        .lineTo(17, 22)
        .lineTo(0, 22)
        .close()
        .revolve()
    )
    flutes = cq.Workplane("XY").polarArray(21, 0, 360, 12).circle(2.6).extrude(17)
    body = body.cut(flutes)
    shaft = cq.Workplane("XY").circle(3.1).extrude(15)
    body = body.cut(shaft)
    grub = cq.Workplane("YZ").workplane(offset=-25).center(0, 8).circle(1.6).extrude(22)
    return body.cut(grub)


# --------------------------------------------------------------------------
# 09 - Shelled enclosure lid
# --------------------------------------------------------------------------
def _build_enclosure_lid() -> cq.Workplane:
    body = cq.Workplane("XY").box(110, 70, 22, centered=(True, True, False))
    body = body.edges("|Z").fillet(8)
    body = body.faces("<Z").shell(-2.5)
    bosses = cq.Workplane("XY").workplane(offset=2.5).rarray(88, 48, 2, 2).circle(5).extrude(17)
    body = body.union(bosses)
    body = (
        body.faces(">Z")
        .workplane(centerOption="CenterOfBoundBox")
        .rarray(88, 48, 2, 2)
        .cskHole(3.4, 6.8, 90, 20)
    )
    vent = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .rarray(9, 1, 5, 1)
        .slot2D(30, 4, 90)
        .extrude(6)
        .translate((0, 0, 20))
    )
    return body.cut(vent)


# --------------------------------------------------------------------------
# 10 - Cable saddle clamp
# --------------------------------------------------------------------------
def _build_cable_saddle_clamp() -> cq.Workplane:
    plate = cq.Workplane("XY").box(56, 26, 7, centered=(True, True, False))
    plate = plate.edges("|Z").fillet(5)
    arch = (
        cq.Workplane("XZ")
        .workplane(offset=-13)
        .moveTo(-15, 7)
        .lineTo(-11, 7)
        .threePointArc((0.0, 18.0), (11.0, 7.0))
        .lineTo(15, 7)
        .threePointArc((0.0, 22.0), (-15.0, 7.0))
        .close()
        .extrude(26)
    )
    body = plate.union(arch)
    holes = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .pushPoints([(-22.0, 0.0), (22.0, 0.0)])
        .circle(2.7)
        .extrude(10)
    )
    body = body.cut(holes)
    tie = cq.Workplane("XZ").workplane(offset=-14).center(0, 20).slot2D(9, 4).extrude(28)
    return body.cut(tie)


# --------------------------------------------------------------------------
# 11 - Threaded pipe cap
# --------------------------------------------------------------------------
def _build_threaded_pipe_cap() -> cq.Workplane:
    body = (
        cq.Workplane("XZ").moveTo(0, 0).lineTo(17, 0).lineTo(17, 30).lineTo(0, 30).close().revolve()
    )
    body = body.faces(">Z").edges().chamfer(1.5)
    grip = cq.Workplane("XY").workplane(offset=22).polarArray(17, 0, 360, 10).circle(2.4).extrude(8)
    body = body.cut(grip)
    path = cq.Workplane("XY").add(cq.Wire.makeHelix(3.0, 19.0, 14.0))
    thread = (
        cq.Workplane("XZ")
        .center(14, 0)
        .polygon(3, 3.2)
        .sweep(path, isFrenet=True, transition="round")
    )
    bore = cq.Workplane("XY").workplane(offset=-1).circle(14.0).extrude(21)
    return body.cut(bore).union(thread.intersect(cq.Workplane("XY").circle(15).extrude(20)))


# --------------------------------------------------------------------------
# 12 - Gear blank disc
# --------------------------------------------------------------------------
def _build_gear_blank_disc() -> cq.Workplane:
    body = cq.Workplane("XY").circle(45).extrude(14)
    body = body.edges("%CIRCLE").chamfer(1.5)
    body = body.faces(">Z").workplane().circle(12.5).cutThruAll()
    lightening = cq.Workplane("XY").polarArray(28, 0, 360, 6).circle(6.5).extrude(14)
    body = body.cut(lightening)
    keyway = (
        cq.Workplane("XY").box(8, 3.2, 14, centered=(True, False, False)).translate((0, 12.5, 0))
    )
    body = body.cut(keyway)
    hub = cq.Workplane("YZ").workplane(offset=-46).center(0, 7).circle(2.6).extrude(40)
    return body.cut(hub)


# --------------------------------------------------------------------------
# 13 - Hinge half with knuckles
# --------------------------------------------------------------------------
def _build_hinge_half() -> cq.Workplane:
    leaf = cq.Workplane("XY").box(70, 46, 6, centered=(True, True, False))
    leaf = leaf.edges("|Z and <X").fillet(6)
    knuckles = cq.Workplane("XZ").workplane(offset=-23).center(30, 9).circle(9).extrude(14)
    knuckles = knuckles.union(knuckles.translate((0, -32, 0)))
    web = cq.Workplane("XY").box(12, 46, 6, centered=(True, True, False)).translate((30, 0, 0))
    body = leaf.union(web).union(knuckles)
    pin = cq.Workplane("XZ").workplane(offset=-25).center(30, 9).circle(4.0).extrude(50)
    body = body.cut(pin)
    screws = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .rarray(24, 26, 2, 2)
        .circle(2.6)
        .extrude(9)
        .translate((-12, 0, 0))
    )
    return body.cut(screws)


# --------------------------------------------------------------------------
# 14 - Slotted angle plate
# --------------------------------------------------------------------------
def _build_slotted_angle_plate() -> cq.Workplane:
    base = cq.Workplane("XY").box(90, 44, 7, centered=(True, True, False))
    base = base.edges("|Z").fillet(5)
    wall = cq.Workplane("XY").box(7, 44, 52, centered=(True, True, False)).translate((-41.5, 0, 0))
    wall = wall.edges("|Z").fillet(3)
    body = base.union(wall)
    base_slots = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .rarray(1, 24, 1, 2)
        .slot2D(26, 8)
        .extrude(10)
        .translate((14, 0, 0))
    )
    body = body.cut(base_slots)
    wall_slots = (
        cq.Workplane("YZ")
        .workplane(offset=-50)
        .pushPoints([(0.0, 20.0), (0.0, 40.0)])
        .slot2D(24, 8)
        .extrude(20)
    )
    return body.cut(wall_slots)


# --------------------------------------------------------------------------
# 15 - Spherical ball stud
# --------------------------------------------------------------------------
def _build_ball_stud() -> cq.Workplane:
    shaft = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(11, 0)
        .lineTo(11, 7)
        .lineTo(5, 14)
        .lineTo(5, 31)
        .lineTo(0, 31)
        .close()
        .revolve()
    )
    body = shaft.union(cq.Workplane("XY").workplane(offset=31).sphere(9))
    body = body.edges("%CIRCLE and <Z").chamfer(1.0)
    flats = cq.Workplane("XY").box(30, 30, 7, centered=(True, True, False))
    keep = cq.Workplane("XY").box(15.2, 30, 7, centered=(True, True, False))
    return body.cut(flats.cut(keep))


# --------------------------------------------------------------------------
# 16 - O-ring gland ring
# --------------------------------------------------------------------------
def _build_oring_gland_ring() -> cq.Workplane:
    body = (
        cq.Workplane("XZ")
        .moveTo(20, 0)
        .lineTo(34, 0)
        .lineTo(34, 4)
        .threePointArc((31.0, 6.0), (34.0, 8.0))
        .lineTo(34, 12)
        .lineTo(20, 12)
        .close()
        .revolve()
    )
    body = body.edges("%CIRCLE and (>Z or <Z)").chamfer(0.8)
    dowels = (
        cq.Workplane("XY").workplane(offset=-1).polarArray(27, 30, 360, 3).circle(2.2).extrude(14)
    )
    return body.cut(dowels)


# --------------------------------------------------------------------------
# 17 - Conical funnel adapter
# --------------------------------------------------------------------------
def _build_funnel_adapter() -> cq.Workplane:
    return (
        cq.Workplane("XZ")
        .moveTo(12, 0)
        .lineTo(14.5, 0)
        .lineTo(14.5, 26)
        .lineTo(40, 62)
        .lineTo(44, 62)
        .lineTo(44, 70)
        .lineTo(40.5, 70)
        .lineTo(40.5, 64)
        .lineTo(37.5, 64)
        .lineTo(12, 28)
        .close()
        .revolve()
    )


# --------------------------------------------------------------------------
# 18 - Lofted pull handle
# --------------------------------------------------------------------------
def _build_lofted_pull_handle() -> cq.Workplane:
    lower = cq.Workplane("XY").rect(46, 14).workplane(offset=25).circle(11).loft()
    body = lower.union(lower.mirror("XY", (0, 0, 25)))
    pads = cq.Workplane("XY").box(46, 30, 6, centered=(True, True, False))
    pads = pads.union(
        cq.Workplane("XY").box(46, 30, 6, centered=(True, True, False)).translate((0, 0, 44))
    )
    body = body.union(pads)
    holes = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .pushPoints([(0.0, -11.0), (0.0, 11.0)])
        .circle(2.6)
        .extrude(8)
    )
    body = body.cut(holes)
    return body.cut(holes.translate((0, 0, 44)))


# --------------------------------------------------------------------------
# 19 - Freeform palm rest
# --------------------------------------------------------------------------
def _build_freeform_palm_rest() -> cq.Workplane:
    body = (
        cq.Workplane("XY")
        .ellipse(52, 34)
        .workplane(offset=16)
        .ellipse(44, 27)
        .workplane(offset=12)
        .ellipse(26, 15)
        .loft()
    )
    mount = cq.Workplane("XY").workplane(offset=-1).rarray(60, 1, 2, 1).circle(3.2).extrude(12)
    body = body.cut(mount)
    cavity = cq.Workplane("XY").workplane(offset=-1).ellipse(44, 27).extrude(9)
    return body.cut(cavity)


# --------------------------------------------------------------------------
# 20 - Finned heat sink plate
# --------------------------------------------------------------------------
def _build_finned_heat_sink() -> cq.Workplane:
    base = cq.Workplane("XY").box(84, 60, 6, centered=(True, True, False))
    fins = cq.Workplane("XY").workplane(offset=6).rarray(11, 1, 7, 1).rect(3.2, 56).extrude(26)
    body = base.union(fins)
    holes = cq.Workplane("XY").workplane(offset=-1).rarray(74, 50, 2, 2).circle(2.2).extrude(8)
    return body.cut(holes)


# --------------------------------------------------------------------------
# 21 - Dovetail slide block
# --------------------------------------------------------------------------
def _build_dovetail_slide_block() -> cq.Workplane:
    body = cq.Workplane("XY").box(70, 48, 26, centered=(True, True, False))
    dovetail = (
        cq.Workplane("YZ")
        .workplane(offset=-36)
        .moveTo(-16, 26)
        .lineTo(16, 26)
        .lineTo(11, 14)
        .lineTo(-11, 14)
        .close()
        .extrude(72)
    )
    body = body.cut(dovetail)
    gib = cq.Workplane("XY").workplane(offset=-1).rarray(40, 1, 2, 1).circle(3.0).extrude(16)
    body = body.cut(gib)
    lube = cq.Workplane("XZ").workplane(offset=-25).center(0, 8).slot2D(30, 6).extrude(12)
    return body.cut(lube)


# --------------------------------------------------------------------------
# 22 - Countersunk corner brace
# --------------------------------------------------------------------------
def _build_corner_brace_csk() -> cq.Workplane:
    base = cq.Workplane("XY").box(60, 40, 6, centered=(True, True, False))
    base = base.edges("|Z").fillet(7)
    wall = cq.Workplane("XY").box(6, 40, 48, centered=(True, True, False)).translate((-27, 0, 0))
    wall = wall.edges("|Z").fillet(2)
    body = base.union(wall)
    body = body.edges(">Z and |Y").chamfer(1.0)
    body = (
        body.faces(">Z[-1]")
        .workplane(centerOption="CenterOfBoundBox")
        .pushPoints([(6.0, -12.0), (6.0, 12.0)])
        .cskHole(4.5, 9.0, 90, 10)
    )
    wall_holes = (
        cq.Workplane("YZ")
        .workplane(offset=-35)
        .pushPoints([(-12.0, 22.0), (12.0, 22.0), (0.0, 40.0)])
        .circle(2.4)
        .extrude(20)
    )
    return body.cut(wall_holes)


# --------------------------------------------------------------------------
# 23 - Split tube clamp
# --------------------------------------------------------------------------
def _build_split_tube_clamp() -> cq.Workplane:
    body = (
        cq.Workplane("XZ")
        .moveTo(16, 0)
        .lineTo(28, 0)
        .lineTo(28, 24)
        .lineTo(16, 24)
        .close()
        .revolve()
    )
    body = body.edges("%CIRCLE and (>Z or <Z)").chamfer(0.8)
    ears = cq.Workplane("XY").box(52, 16, 24, centered=(True, True, False)).translate((0, 20, 0))
    body = body.union(ears)
    gap = cq.Workplane("XY").box(3, 30, 24, centered=(True, True, False)).translate((0, 18, 0))
    body = body.cut(gap)
    bolts = (
        cq.Workplane("YZ")
        .workplane(offset=-30)
        .pushPoints([(20.0, 8.0), (20.0, 16.0)])
        .circle(2.6)
        .extrude(60)
    )
    return body.cut(bolts)


# --------------------------------------------------------------------------
# 24 - Tube end cap with boss
# --------------------------------------------------------------------------
def _build_end_cap_boss() -> cq.Workplane:
    disc = cq.Workplane("XY").circle(25).extrude(8)
    disc = disc.faces(">Z").edges().fillet(2.5)
    disc = disc.faces("<Z").edges().chamfer(1.0)
    boss = cq.Workplane("XY").workplane(offset=8).circle(11).extrude(14)
    body = disc.union(boss)
    body = body.faces(">Z").edges().fillet(2.0)
    blind = cq.Workplane("XY").workplane(offset=22).circle(4.5).extrude(-13)
    body = body.cut(blind)
    cross = cq.Workplane("YZ").workplane(offset=-20).center(0, 16).circle(2.0).extrude(40)
    body = body.cut(cross)
    vent = cq.Workplane("XY").workplane(offset=-1).polarArray(18, 0, 360, 4).circle(2.0).extrude(6)
    return body.cut(vent)


# --------------------------------------------------------------------------
# 25 - Engraved label plate
# --------------------------------------------------------------------------
def _build_engraved_label_plate() -> cq.Workplane:
    body = cq.Workplane("XY").box(90, 34, 5, centered=(True, True, False))
    body = body.edges("|Z").fillet(4)
    recess = cq.Workplane("XY").workplane(offset=4).rect(78, 22).extrude(2)
    body = body.cut(recess)
    strokes = [
        (-32.0, 0.0, 2.0, 12.0),
        (-27.0, -5.0, 8.0, 2.0),
        (-18.0, 0.0, 2.0, 12.0),
        (-13.0, 5.0, 8.0, 2.0),
        (-13.0, -5.0, 8.0, 2.0),
        (-4.0, 0.0, 2.0, 12.0),
        (1.0, 5.0, 8.0, 2.0),
        (10.0, 0.0, 2.0, 12.0),
        (15.0, 0.0, 8.0, 2.0),
        (24.0, 0.0, 2.0, 12.0),
        (29.0, -5.0, 8.0, 2.0),
    ]
    for x, y, w, h in strokes:
        cutter = cq.Workplane("XY").workplane(offset=3.6).rect(w, h).extrude(2).translate((x, y, 0))
        body = body.cut(cutter)
    holes = cq.Workplane("XY").workplane(offset=-1).rarray(80, 1, 2, 1).circle(2.2).extrude(8)
    return body.cut(holes)


# --------------------------------------------------------------------------
# 26 - Wheel hub adapter
# --------------------------------------------------------------------------
def _build_wheel_hub_adapter() -> cq.Workplane:
    body = (
        cq.Workplane("XZ")
        .moveTo(15, 0)
        .lineTo(60, 0)
        .lineTo(60, 9)
        .lineTo(34, 9)
        .lineTo(34, 26)
        .lineTo(15, 26)
        .close()
        .revolve()
    )
    body = body.faces(">Z").edges().fillet(2.0)
    body = (
        body.faces("<Z")
        .workplane(centerOption="CenterOfBoundBox")
        .polarArray(46, 0, 360, 5)
        .cboreHole(10.5, 17.0, 5.0)
    )
    return body.edges("%CIRCLE and <Z").chamfer(1.0)


# --------------------------------------------------------------------------
# 27 - Sensor mounting bracket
# --------------------------------------------------------------------------
def _build_sensor_bracket() -> cq.Workplane:
    base = cq.Workplane("XY").box(52, 30, 5, centered=(True, True, False))
    base = base.edges("|Z").fillet(6)
    tab = cq.Workplane("XY").box(5, 30, 40, centered=(True, True, False)).translate((23.5, 0, 0))
    tab = tab.edges("|Z").fillet(2.4)
    body = base.union(tab)
    body = body.edges(">Z and |Y").chamfer(1.0)
    base_slot = (
        cq.Workplane("XY").workplane(offset=-1).slot2D(20, 6).extrude(8).translate((-12, 0, 0))
    )
    body = body.cut(base_slot)
    tab_slot = cq.Workplane("YZ").workplane(offset=18).center(0, 26).slot2D(18, 6).extrude(14)
    body = body.cut(tab_slot)
    pilot = (
        cq.Workplane("XY")
        .workplane(offset=5)
        .pushPoints([(-22.0, -10.0), (-22.0, 10.0)])
        .circle(1.8)
        .extrude(-3.5)
    )
    return body.cut(pilot)


# --------------------------------------------------------------------------
# 28 - Hydraulic manifold block
# --------------------------------------------------------------------------
def _build_manifold_block() -> cq.Workplane:
    body = cq.Workplane("XY").box(76, 46, 38, centered=(True, True, False))
    body = body.edges("|Z").fillet(4)
    body = body.edges(">Z or <Z").chamfer(1.2)
    body = (
        body.faces(">Z")
        .workplane(centerOption="CenterOfBoundBox")
        .rarray(44, 1, 2, 1)
        .cboreHole(8.0, 14.0, 6.0, 26)
    )
    cross = cq.Workplane("YZ").workplane(offset=-40).center(0, 12).circle(4.0).extrude(80)
    body = body.cut(cross)
    blind_port = cq.Workplane("XZ").workplane(offset=-24).center(0, 26).circle(5.0).extrude(16)
    body = body.cut(blind_port)
    pocket = cq.Workplane("XY").workplane(offset=-1).rect(46, 26).extrude(7)
    body = body.cut(pocket)
    mounts = cq.Workplane("XY").workplane(offset=-1).rarray(64, 34, 2, 2).circle(2.6).extrude(42)
    return body.cut(mounts)


PARTS: tuple[PartSpec, ...] = (
    PartSpec(
        slug="l-bracket-gusset",
        title="Gusseted L bracket",
        tags=(
            "prismatic-multi-axis",
            "through-hole",
            "rib",
            "fillet-vertical",
            "chamfer",
        ),
        build=_build_l_bracket_gusset,
        notes=(
            "A triangular gusset meets the base and wall at three different "
            "angles, so the tangent-plane clustering has to separate a sloped "
            "rib face from two orthogonal plates."
        ),
    ),
    PartSpec(
        slug="flange-four-bolt",
        title="Four-bolt pipe flange",
        tags=(
            "revolved",
            "through-hole",
            "counterbore",
            "circular-pattern",
            "fillet-rim",
            "chamfer",
        ),
        build=_build_flange_four_bolt,
        notes=(
            "A revolved hub with a filleted rim; the counterbores are cut from "
            "the opposite face to the fillet, which trips up single-axis fits."
        ),
    ),
    PartSpec(
        slug="motor-mount-nema17",
        title="NEMA 17 motor mount",
        tags=(
            "prismatic-multi-axis",
            "through-hole",
            "pocket",
            "slot",
            "linear-pattern",
            "fillet-vertical",
            "chamfer",
        ),
        build=_build_motor_mount_nema17,
        notes=(
            "Bolt pattern and pilot bore are cut along Z while the adjustment "
            "slots are cut along Y, giving two independent extrusion axes."
        ),
    ),
    PartSpec(
        slug="bearing-block-608",
        title="608 bearing pillow block",
        tags=(
            "prismatic-multi-axis",
            "through-hole",
            "blind-hole",
            "counterbore",
            "fillet-vertical",
        ),
        build=_build_bearing_block_608,
        notes=(
            "The bearing bore runs along Y, the foot holes along Z and the "
            "grub screw along Z into the bore, so three axes intersect."
        ),
    ),
    PartSpec(
        slug="hex-standoff-spacer",
        title="Hex standoff spacer",
        tags=("prismatic-single-axis", "through-hole", "chamfer"),
        build=_build_hex_standoff,
        notes=(
            "The easy baseline: one hex profile extruded once, with chamfered "
            "ends and a single axial bore."
        ),
    ),
    PartSpec(
        slug="stepped-shaft-spacer",
        title="Stepped shaft spacer",
        tags=("revolved", "through-hole", "chamfer"),
        build=_build_stepped_shaft_spacer,
        notes=(
            "Three coaxial cylinder steps that a naive fitter is tempted to "
            "merge into one cylinder of averaged radius."
        ),
    ),
    PartSpec(
        slug="v-belt-pulley",
        title="V-belt pulley",
        tags=(
            "revolved",
            "taper",
            "cone",
            "through-hole",
            "blind-hole",
            "slot",
            "prismatic-multi-axis",
        ),
        build=_build_v_belt_pulley,
        notes=(
            "The V groove is a pair of opposed cone faces meeting at a sharp "
            "circle, and the radial grub screw breaks axial symmetry."
        ),
    ),
    PartSpec(
        slug="fluted-control-knob",
        title="Fluted control knob",
        tags=(
            "revolved",
            "circular-pattern",
            "taper",
            "cone",
            "blind-hole",
            "prismatic-multi-axis",
        ),
        build=_build_fluted_knob,
        notes=(
            "Twelve scalloped flutes leave narrow slivers of the original "
            "cylinder between them, which mesh segmentation likes to drop."
        ),
    ),
    PartSpec(
        slug="enclosure-lid-shell",
        title="Shelled enclosure lid",
        tags=(
            "shell",
            "thin-wall",
            "boss",
            "countersink",
            "slot",
            "linear-pattern",
            "fillet-vertical",
            "prismatic-multi-axis",
        ),
        build=_build_enclosure_lid,
        notes=(
            "A 2.5 mm shell means inner and outer faces are offset pairs; the "
            "countersinks and vent slots then perforate the thin wall."
        ),
    ),
    PartSpec(
        slug="cable-saddle-clamp",
        title="Cable saddle clamp",
        tags=(
            "prismatic-multi-axis",
            "thin-wall",
            "through-hole",
            "slot",
            "fillet-vertical",
        ),
        build=_build_cable_saddle_clamp,
        notes=(
            "A half-annular arch extruded along Y sits on a plate drilled "
            "along Z, and a tie slot cuts the arch crown."
        ),
    ),
    PartSpec(
        slug="threaded-pipe-cap",
        title="Threaded pipe cap",
        tags=(
            "thread-like",
            "revolved",
            "circular-pattern",
            "thin-wall",
            "chamfer",
        ),
        build=_build_threaded_pipe_cap,
        notes=(
            "A helical swept thread inside a knurl-cut cap: the thread is a "
            "genuinely non-analytic sweep surface, out of scope for prismatic "
            "reconstruction."
        ),
    ),
    PartSpec(
        slug="gear-blank-disc",
        title="Gear blank disc",
        tags=(
            "revolved",
            "circular-pattern",
            "through-hole",
            "slot",
            "chamfer",
            "prismatic-multi-axis",
        ),
        build=_build_gear_blank_disc,
        notes=(
            "Six lightening holes on a bolt circle plus a keyway that breaks "
            "the bore into a non-circular profile."
        ),
    ),
    PartSpec(
        slug="hinge-half-knuckle",
        title="Hinge half with knuckles",
        tags=(
            "prismatic-multi-axis",
            "linear-pattern",
            "through-hole",
            "fillet-vertical",
        ),
        build=_build_hinge_half,
        notes=(
            "Two knuckles extruded along Y are welded to a leaf extruded "
            "along Z; the pin bore is coaxial with the knuckles."
        ),
    ),
    PartSpec(
        slug="slotted-angle-plate",
        title="Slotted angle plate",
        tags=(
            "prismatic-multi-axis",
            "slot",
            "linear-pattern",
            "fillet-vertical",
        ),
        build=_build_slotted_angle_plate,
        notes=(
            "Slots in both flanges are patterned on perpendicular planes, so "
            "the slot end caps are half-cylinders about two different axes."
        ),
    ),
    PartSpec(
        slug="spherical-ball-stud",
        title="Spherical ball stud",
        tags=("sphere", "revolved", "cone", "taper", "chamfer", "prismatic-multi-axis"),
        build=_build_ball_stud,
        notes=(
            "A true spherical head on a tapered neck, with wrench flats milled "
            "along X - three surface families on one small part."
        ),
    ),
    PartSpec(
        slug="oring-gland-ring",
        title="O-ring gland ring",
        tags=("torus", "revolved", "circular-pattern", "blind-hole", "chamfer"),
        build=_build_oring_gland_ring,
        notes=(
            "The seal groove is a real toroidal face; fitting it as a cylinder "
            "or cone changes the sealing dimension."
        ),
    ),
    PartSpec(
        slug="conical-funnel-adapter",
        title="Conical funnel adapter",
        tags=("cone", "revolved", "taper", "thin-wall"),
        build=_build_funnel_adapter,
        notes=(
            "A 2.5 mm wall revolved cone: the inner and outer cone faces have "
            "the same half-angle but different apex positions."
        ),
    ),
    PartSpec(
        slug="lofted-pull-handle",
        title="Lofted pull handle",
        tags=("freeform", "through-hole", "prismatic-multi-axis"),
        build=_build_lofted_pull_handle,
        notes=(
            "The grip is a rectangle-to-circle-to-rectangle loft, so the body "
            "is a B-spline surface with no analytic fit at all."
        ),
    ),
    PartSpec(
        slug="freeform-palm-rest",
        title="Freeform palm rest",
        tags=("freeform", "pocket", "through-hole"),
        build=_build_freeform_palm_rest,
        notes=(
            "Three elliptical sections lofted into a doubly curved shell; the "
            "hollow underside keeps the wall thin so normals vary quickly."
        ),
    ),
    PartSpec(
        slug="finned-heat-sink",
        title="Finned heat sink plate",
        tags=("prismatic-single-axis", "linear-pattern", "rib", "through-hole"),
        build=_build_finned_heat_sink,
        notes=(
            "Seven thin fins on a shared base: the narrow channels between "
            "them are where mesh decimation loses parallelism."
        ),
    ),
    PartSpec(
        slug="dovetail-slide-block",
        title="Dovetail slide block",
        tags=("prismatic-multi-axis", "taper", "slot", "through-hole"),
        build=_build_dovetail_slide_block,
        notes=(
            "The dovetail flanks are sloped planes cut along X while the gib "
            "holes and lube slot come from Z and Y."
        ),
    ),
    PartSpec(
        slug="corner-brace-countersunk",
        title="Countersunk corner brace",
        tags=(
            "prismatic-multi-axis",
            "countersink",
            "through-hole",
            "fillet-vertical",
            "chamfer",
        ),
        build=_build_corner_brace_csk,
        notes=(
            "Countersinks on the top face and plain holes through the wall "
            "give two distinct hole archetypes on one small bracket."
        ),
    ),
    PartSpec(
        slug="split-tube-clamp",
        title="Split tube clamp",
        tags=(
            "revolved",
            "prismatic-multi-axis",
            "slot",
            "through-hole",
            "chamfer",
        ),
        build=_build_split_tube_clamp,
        notes=(
            "A revolved sleeve with a milled split and cross-drilled pinch "
            "bolts, so the bore is only nearly closed."
        ),
    ),
    PartSpec(
        slug="tube-end-cap-boss",
        title="Tube end cap with boss",
        tags=(
            "boss",
            "blind-hole",
            "fillet-rim",
            "circular-pattern",
            "chamfer",
            "prismatic-multi-axis",
        ),
        build=_build_end_cap_boss,
        notes=(
            "A filleted boss-to-disc junction produces a torus blend face "
            "that is easy to mistake for part of the boss cylinder."
        ),
    ),
    PartSpec(
        slug="engraved-label-plate",
        title="Engraved label plate",
        tags=("text-like", "pocket", "prismatic-single-axis", "fillet-vertical"),
        build=_build_engraved_label_plate,
        notes=(
            "Eleven shallow 2 mm strokes inside a recessed panel imitate "
            "engraved lettering - many tiny coplanar faces at one depth."
        ),
    ),
    PartSpec(
        slug="wheel-hub-adapter",
        title="Wheel hub adapter",
        tags=(
            "revolved",
            "circular-pattern",
            "counterbore",
            "through-hole",
            "fillet-rim",
            "chamfer",
        ),
        build=_build_wheel_hub_adapter,
        notes=(
            "Five counterbored studs on an odd-count bolt circle, so no "
            "mirror symmetry can be exploited to clean up the fit."
        ),
    ),
    PartSpec(
        slug="sensor-mount-bracket",
        title="Sensor mounting bracket",
        tags=(
            "prismatic-multi-axis",
            "slot",
            "through-hole",
            "blind-hole",
            "fillet-vertical",
            "chamfer",
        ),
        build=_build_sensor_bracket,
        notes=(
            "A small bracket where the adjustment slots run along Z and X and "
            "the pilot holes stop blind inside a 5 mm plate."
        ),
    ),
    PartSpec(
        slug="hydraulic-manifold-block",
        title="Hydraulic manifold block",
        tags=(
            "prismatic-multi-axis",
            "counterbore",
            "through-hole",
            "blind-hole",
            "pocket",
            "chamfer",
            "fillet-vertical",
        ),
        build=_build_manifold_block,
        notes=(
            "Ports drilled from three orthogonal faces intersect inside the "
            "block, producing partial cylinder faces with curved seams."
        ),
    ),
)


def get_part(slug: str) -> PartSpec:
    """Return the :class:`PartSpec` with ``slug``.

    Raises:
        KeyError: if no part in :data:`PARTS` has that slug.
    """
    for spec in PARTS:
        if spec.slug == slug:
            return spec
    raise KeyError(f"unknown part slug: {slug!r}")

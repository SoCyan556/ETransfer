bl_info = {
    "name": "ETransfer", "author": "Cyan",
    "version": (1, 3, 1), "blender": (4, 1, 0),
    "location": "3D View > Sidebar > ETransfer",
    "description": "Transfer a body shape key to fitted clothing using surface displacement",
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty, StringProperty, FloatProperty, EnumProperty
from mathutils.bvhtree import BVHTree


def mesh_object(self, obj):
    return obj.type == 'MESH'


def barycentric(p, a, b, c):
    u, v, w = b - a, c - a, p - a
    uu, uv, vv = u.dot(u), u.dot(v), v.dot(v)
    den = uu * vv - uv * uv
    if abs(den) < 1e-20:
        return (1.0, 0.0, 0.0)
    y = (vv * w.dot(u) - uv * w.dot(v)) / den
    z = (uu * w.dot(v) - uv * w.dot(u)) / den
    weights = [max(0.0, 1.0 - y - z), max(0.0, y), max(0.0, z)]
    total = sum(weights)
    return tuple(x / total for x in weights)


class ET_Settings(bpy.types.PropertyGroup):
    source: PointerProperty(name="Source mesh", type=bpy.types.Object, poll=mesh_object)
    target: PointerProperty(name="Target mesh", type=bpy.types.Object, poll=mesh_object)
    mode: EnumProperty(name="Transfer", items=[
        ('SINGLE', "Single Shape Key", "Transfer the chosen shape key"),
        ('ALL', "All Shape Keys", "Transfer every non-Basis key; skip existing names"),
    ], default='SINGLE')
    key_name: StringProperty(name="Source shape key", default="Heeled")
    max_distance: FloatProperty(name="Maximum distance", default=0.05, min=0.00001,
                               subtype='DISTANCE', description="Skip clothing vertices farther from the body, in world units")
    strength: FloatProperty(name="Strength", default=1.0, min=0.0, max=2.0)


class ET_OT_Transfer(bpy.types.Operator):
    bl_idname = "object.etransfer_transfer"
    bl_label = "Transfer Shape Key"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.etransfer_settings
        body, clothing = s.source, s.target
        try:
            if context.mode != 'OBJECT':
                raise ValueError("Switch to Object Mode first")
            if not body or not clothing or body == clothing:
                raise ValueError("Choose two different mesh objects")
            if clothing.data.users > 1:
                raise ValueError("Make the clothing mesh single-user first")
            if ((clothing.library and not clothing.override_library) or
                    (clothing.data.library and not clothing.data.override_library)):
                raise ValueError("Clothing must be locally editable")
            keys = body.data.shape_keys
            if not keys or not keys.use_relative:
                raise ValueError("Body needs relative shape keys")
            selected = ([k for k in keys.key_blocks if k != keys.reference_key]
                        if s.mode == 'ALL' else [keys.key_blocks.get(s.key_name)])
            if not selected or any(k is None or k == keys.reference_key for k in selected):
                raise ValueError("Choose an existing non-Basis source shape key")
            target_keys = clothing.data.shape_keys
            if target_keys and not target_keys.use_relative:
                raise ValueError("Target needs relative shape keys")
            skipped = sum(1 for k in selected if target_keys and target_keys.key_blocks.get(k.name))
            selected = [k for k in selected if not target_keys or not target_keys.key_blocks.get(k.name)]
            if not selected:
                raise ValueError("Target already has these keys; rename or remove them to transfer again")
            for key in selected:
                if key.vertex_group and body.vertex_groups.get(key.vertex_group) is None:
                    raise ValueError(f"Missing source vertex group for {key.name}")
            if abs(clothing.matrix_world.determinant()) < 1e-12:
                raise ValueError("Clothing has a zero scale")

            # Match undeformed Basis surfaces; ignore live poses and modifiers.
            matrix = body.matrix_world
            basis = keys.reference_key
            positions = [matrix @ v.co for v in basis.data]
            linear = matrix.to_3x3()
            body.data.calc_loop_triangles()
            triangles = [tuple(t.vertices) for t in body.data.loop_triangles]
            if not triangles:
                raise ValueError("Body has no faces")
            tree = BVHTree.FromPolygons(positions, triangles, all_triangles=True)
            target_basis = (target_keys.reference_key.data if target_keys else clothing.data.vertices)
            inverse = clothing.matrix_world.inverted().to_3x3()
            # Cache each target vertex's source triangle once for the whole batch.
            mapping, base_coords, matched = [], [], 0
            for vertex in target_basis:
                co = vertex.co.copy()
                base_coords.append(co)
                p, normal, index, distance = tree.find_nearest(clothing.matrix_world @ co, s.max_distance)
                if index is not None:
                    ids = triangles[index]
                    mapping.append((ids, barycentric(p, *(positions[i] for i in ids))))
                    matched += 1
                else:
                    mapping.append(None)
            if not matched:
                raise ValueError("No vertices matched. Check alignment or increase maximum distance")
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        created = []
        basis_added = False
        try:
            if not clothing.data.shape_keys:
                clothing.shape_key_add(name="Basis", from_mix=False)
                basis_added = True
            for key in selected:
                mask = body.vertex_groups.get(key.vertex_group) if key.vertex_group else None
                deltas = []
                for i, v in enumerate(key.data):
                    weight = 1.0
                    if mask:
                        try:
                            weight = mask.weight(i)
                        except RuntimeError:
                            weight = 0.0
                    deltas.append(linear @ (v.co - key.relative_key.data[i].co) * weight)
                output = clothing.shape_key_add(name=key.name, from_mix=False)
                created.append(output)
                output.relative_key = clothing.data.shape_keys.reference_key
                output.slider_min, output.slider_max = key.slider_min, key.slider_max
                for vertex, co, match in zip(output.data, base_coords, mapping):
                    result = co.copy()
                    if match:
                        ids, weights = match
                        displacement = sum((deltas[i] * w for i, w in zip(ids, weights)), deltas[ids[0]] * 0)
                        result += inverse @ displacement * s.strength
                    vertex.co = result
                output.value = 0.0
        except Exception as exc:
            for output in reversed(created):
                clothing.shape_key_remove(output)
            if basis_added:
                clothing.shape_key_remove(clothing.data.shape_keys.reference_key)
            self.report({'ERROR'}, f"Transfer rolled back: {exc}")
            return {'CANCELLED'}
        clothing.active_shape_key_index = len(clothing.data.shape_keys.key_blocks) - 1
        clothing.data.update()
        self.report({'INFO'}, f"Created {len(created)} keys; skipped {skipped} existing; {matched}/{len(mapping)} vertices matched")
        return {'FINISHED'}


class ET_PT_Panel(bpy.types.Panel):
    bl_label = "ETransfer"
    bl_idname = "ET_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ETransfer"

    def draw(self, context):
        layout = self.layout
        s = context.scene.etransfer_settings
        layout.prop(s, "source")
        layout.prop(s, "target")
        layout.prop(s, "mode")
        if s.mode == 'SINGLE':
            if s.source and s.source.data.shape_keys:
                layout.prop_search(s, "key_name", s.source.data.shape_keys, "key_blocks")
            else:
                layout.prop(s, "key_name")
        else:
            layout.label(text="Existing key names are skipped.")
        layout.prop(s, "max_distance")
        layout.prop(s, "strength")
        layout.operator(ET_OT_Transfer.bl_idname, text="Transfer All Shape Keys" if s.mode == 'ALL' else "Transfer Shape Key")
        layout.label(text="Use fitted meshes in their rest position.")
        layout.label(text="Preview by setting both keys to 1.")


CLASSES = (ET_Settings, ET_OT_Transfer, ET_PT_Panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.etransfer_settings = PointerProperty(type=ET_Settings)


def unregister():
    del bpy.types.Scene.etransfer_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()

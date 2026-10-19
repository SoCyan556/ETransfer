# ETransfer

ETransfer is a Blender add-on for moving body shape keys onto fitted clothing. It matches clothing vertices to the nearest point on the body's undeformed surface, then transfers the body's displacement to the clothing.

## Requirements

- Blender 4.1 or newer
- A body and clothing mesh aligned in the same rest position
- Relative shape keys on the source body
- Locally editable, single-user mesh data on the target clothing

ETransfer uses only Blender's built-in Python modules. No external Python packages are required.

## Installation

1. Download `etransfer.py` from this repository.
2. In Blender, open **Edit > Preferences > Add-ons**.
3. Click **Install from Disk** and select `etransfer.py`.
4. Enable **Object: ETransfer**.
5. Open the 3D View sidebar with `N` and select the **ETransfer** tab.

## Transferring shape keys

1. Put the body and clothing in their undeformed rest position.
2. Choose the body as **Source mesh** and the fitted clothing as **Target mesh**.
3. Select a single source shape key, or choose **All Shape Keys**.
4. Set **Maximum distance** high enough to reach the clothing without catching unrelated geometry.
5. Adjust **Strength** if necessary, then run the transfer.

Existing shape-key names on the target are skipped in batch mode. ETransfer does not overwrite them.

## Important notes

- Work on a copy of important meshes until you are comfortable with the results.
- Apply or account for object transforms before transferring between unusually scaled objects.
- A very large maximum distance can match clothing to the wrong part of the body.
- Live modifiers and poses are intentionally ignored; ETransfer works from Basis geometry.

## AI assistance

This project was created with AI assistance. We understand why some people are uncomfortable with AI-assisted work, including concerns around attribution, labor, training data, and low-effort generated projects. The source is provided openly so it can be inspected, changed, or avoided according to your own preferences.

## License

ETransfer is available under the MIT License. See [LICENSE](LICENSE).

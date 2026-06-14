# Data

The bot runtime depends on the curated data files in `data/curated_space_objects/`.

Required files:

- `space_objects_data.csv` - localized object metadata and image paths.
- `space_object_embeddings.npy` - precomputed CLIP image embeddings for objects.
- `space_object_person_bias.npy` - calibration bias used to reduce generic face-photo matches.
- `images/` - local object images referenced by the CSV.
- `schedule_ru.txt` - editable Russian-language camp schedule served by `/schedule` (re-read on every call, no restart needed).
- `schedule_en.txt` - same schedule in English.

The CSV expects these columns:

- `name_en`
- `name_ru`
- `mood_en`
- `mood_ru`
- `description_en`
- `description_ru`
- `object_type_en`
- `object_type_ru`
- `image_path`

Run this before deploying data changes:

```bash
python scripts/check_runtime.py
```

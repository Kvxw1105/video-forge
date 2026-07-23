# Generated Assets Layout

After an item pauses, place generated scene files in one folder per item:

```text
item-a-generated/
  scene_001.png
  scene_002.mp4
  scene_003.png

item-b-generated/
  scene_001.png
  scene_002.mp4
  scene_003.png
```

Import each folder only for its matching Factory item. Files are copied into
that project's asset directory; an import never binds assets across projects.
Use the `pending-visuals` response rather than guessing the expected Scene
count or filename order.

Ohio crosswalk support files

These Census/TIGER inputs were added to support the NHGIS block crosswalk files already in `data/`:

- `nhgis_blk2000_blk2010_39.zip`
  Needs `tl_2010_39_tabblock10` as the 2010 block target geometry.
- `nhgis_blk2010_blk2020_39.zip`
  Needs both `tl_2010_39_tabblock10` and `tl_2020_39_tabblock20` when allocating 2010 blocks forward to 2020 blocks.
- `nhgis_blk2020_blk2010_39.zip`
  Needs both `tl_2020_39_tabblock20` and `tl_2010_39_tabblock10` when allocating modern block-based data back to 2010 blocks.

Downloaded official Census/TIGER support layers:

- `tl_2010_39_county10.geojson`
- `tl_2020_39_county20.geojson`
- `tl_2010_39_tabblock10/`
- `tl_2020_39_tabblock20/`

Downloaded official district layers used by the app and by future precinct-to-district crosswalk work:

- `../tileset/oh_cd118_2020.geojson`
- `../tileset/oh_cd118.geojson`
- `../tileset/oh_cd119.geojson`
- `../tileset/oh_state_house_2020.geojson`
- `../tileset/oh_state_house_2024.geojson`
- `../tileset/oh_state_senate_2020.geojson`
- `../tileset/oh_state_senate_2024.geojson`

Fetcher script:

- `scripts/fetch_ohio_census_geographies.py`

Inventory script and latest snapshot:

- `scripts/inspect_ohio_crosswalk_inputs.py`
- `data/census/ohio_crosswalk_inventory.json`

District carryover crosswalk generator and outputs:

- `scripts/build_district_crosswalks.py`
- `data/crosswalks/README.md`
- `data/crosswalks/district_crosswalk_manifest.json`

Note:

- NHGIS block crosswalks help translate Census blocks across vintages. They do not replace a precinct or VTD boundary layer when we need to join election precinct rows onto map shapes.
- Ohio 2010 VTD geometry is available from the official Census TIGER directory, but it is published county-by-county rather than as one statewide zip. The fetcher now supports this as dataset key `vtd10`.
- A straightforward Ohio 2020 statewide VTD TIGER zip was not available at the expected Census path, and the Census 2000 VTD directory did not show Ohio county files during verification. That means older/legacy precinct geometry may still need a different official state source if we want a true 2000 precinct layer.

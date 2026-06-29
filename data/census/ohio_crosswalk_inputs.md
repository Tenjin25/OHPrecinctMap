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

Note:

The repo still does not have an Ohio precinct/VTD boundary file wired for the precinct overlay. Census tabblock and district geometry needed for the NHGIS crosswalk workflow are now present, but precinct-level overlay/crosswalk generation will still need an Ohio precinct or VTD source to join election rows onto map shapes.

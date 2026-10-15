-- Community Plan Areas where LAMC Chapter 1A (the new Zoning Code) governs. Everywhere else is Chapter I.
-- Re-check this list whenever a Community Plan update is adopted.
INSERT INTO code_regime_area (community_plan_area, regime, effective_date, citation, verified) VALUES
  ('Downtown', '1A', '2025-01-27',
   'Ord. 188,418 (Chapter 1A), effective 2025-01-20, operative 2025-01-27; https://zoning.lacity.gov/sites/default/files/zcode_download/article_1.pdf (retrieved 2026-10-15)',
   true),
  ('Boyle Heights', '1A', '2026-08-20',
   'zoning.lacity.gov: "currently in effect within the Downtown and Boyle Heights Community Plan Areas" (retrieved 2026-10-15). Effective date 2026-08-20 from secondary reporting; confirm against the ordinance.',
   false);

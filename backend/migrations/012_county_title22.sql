-- A second jurisdiction: LA County Title 22 (unincorporated areas) as a code chapter beside LAMC Chapters I and 1A.
ALTER TABLE reg_document DROP CONSTRAINT reg_document_code_chapter_check;
ALTER TABLE reg_document ADD CONSTRAINT reg_document_code_chapter_check CHECK (code_chapter IN ('I', '1A', 'T22'));
ALTER TABLE reg_chunk DROP CONSTRAINT reg_chunk_code_chapter_check;
ALTER TABLE reg_chunk ADD CONSTRAINT reg_chunk_code_chapter_check CHECK (code_chapter IN ('I', '1A', 'T22'));

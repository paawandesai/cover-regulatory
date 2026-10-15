-- Hybrid search support: which model produced each embedding, and an HNSW index for cosine distance.
ALTER TABLE reg_chunk ADD COLUMN embedding_model text;
CREATE INDEX reg_chunk_embedding_idx ON reg_chunk USING hnsw (embedding vector_cosine_ops);

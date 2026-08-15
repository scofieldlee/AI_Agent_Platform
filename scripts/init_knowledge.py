"""
Initialize knowledge base and sync from Obsidian vault.

Usage:
    .venv/bin/python scripts/init_knowledge.py

Steps:
1. Create knowledge base record (if not exists)
2. Sync from Obsidian vault -> chunks + embeddings
3. Print sync statistics
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from app.database.session import async_session_factory
    from app.models.knowledge import KnowledgeBase
    from sqlalchemy import select

    # Step 1: Create knowledge base
    print("=" * 60)
    print("Step 1: Create knowledge base")
    print("=" * 60)

    async with async_session_factory() as session:
        # Check if KB already exists
        result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.code == "ruko_product_kb")
        )
        kb = result.scalars().first()

        if kb:
            print(f"Knowledge base already exists: {kb.name} (ID={kb.id})")
            print(f"  Documents: {kb.document_count}, Chunks: {kb.chunk_count}")
        else:
            kb = KnowledgeBase(
                name="Ruko 商品知识库",
                code="ruko_product_kb",
                description="Ruko品牌无人机/遥控玩具商品知识库，包含商品档案、FAQ、售后信息",
                kb_type="product",
                source_type="obsidian",
                source_path="/Users/scofieldlee/Desktop/Project/obsidian/study/study",
                config={
                    "chunk_size": 500,
                    "chunk_overlap": 50,
                    "embedding_model": "BAAI/bge-small-zh-v1.5",
                },
            )
            session.add(kb)
            await session.commit()
            await session.refresh(kb)
            print(f"Knowledge base created: {kb.name} (ID={kb.id})")

    # Step 2: Sync
    print()
    print("=" * 60)
    print("Step 2: Sync from Obsidian vault")
    print("=" * 60)

    from app.knowledge.services.sync_service import KnowledgeSyncService
    service = KnowledgeSyncService()

    try:
        stats = await service.sync_knowledge_base(kb.id, force=True)
        print()
        print("Sync completed!")
        print(f"  Documents scanned:  {stats['documents_scanned']}")
        print(f"  Documents created:  {stats['documents_created']}")
        print(f"  Documents updated:  {stats['documents_updated']}")
        print(f"  Documents unchanged: {stats['documents_unchanged']}")
        print(f"  Chunks created:     {stats['chunks_created']}")
        print(f"  Errors:             {len(stats['errors'])}")

        if stats["errors"]:
            print()
            print("Errors:")
            for err in stats["errors"][:5]:
                print(f"  - {err['document']}: {err['error']}")

    except Exception as e:
        print(f"Sync failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 3: Verify
    print()
    print("=" * 60)
    print("Step 3: Verify")
    print("=" * 60)

    from sqlalchemy import text
    async with async_session_factory() as session:
        # Count chunks with embeddings
        result = await session.execute(
            text("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
        )
        chunk_count = result.scalar()
        print(f"Chunks with embeddings: {chunk_count}")

        # Sample search
        if chunk_count > 0:
            print()
            print("Sample vector search test:")
            from app.models_center.service import ModelService
            model_service = ModelService()

            query = "无人机有什么特点"
            print(f"  Query: {query}")

            query_emb = await model_service.embed([query])
            query_vec = query_emb[0]

            result = await session.execute(
                text("""
                    SELECT content, section, metadata as meta,
                           1 - (embedding <=> CAST(:vec AS vector)) as score
                    FROM chunks
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:vec AS vector)
                    LIMIT 3
                """),
                {"vec": str(query_vec)}
            )
            rows = result.fetchall()

            for i, row in enumerate(rows):
                meta = row.meta if row.meta else {}
                title = meta.get("title", "Unknown") if isinstance(meta, dict) else "Unknown"
                print(f"  [{i+1}] {title} - {row.section} (score={row.score:.4f})")
                print(f"      {row.content[:100]}...")

    print()
    print("=" * 60)
    print("Done! Knowledge base is ready for RAG conversations.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

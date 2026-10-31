import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from src.db.db_connection import AsyncSessionLocal  # noqa: E402
from src.repositories.agent_profile_repo import AgentProfileRepository  # noqa: E402
from src.repositories.knowledge_pack_repo import KnowledgePackRepository  # noqa: E402
from src.repositories.skill_repo import SkillRepository  # noqa: E402
from src.repositories.tool_repo import ToolDefinitionRepository  # noqa: E402

BIG = 100_000


def _row(id_, name, description):
    return {"id": id_, "name": name, "description": description or ""}


async def main(out: str) -> None:
    async with AsyncSessionLocal() as session:
        skills = await SkillRepository(session).admin_list_global(limit=BIG)
        tools = await ToolDefinitionRepository(session).admin_list(limit=BIG)
        packs = await KnowledgePackRepository(session).list_active(limit=BIG)
        profiles = await AgentProfileRepository(session).list_active(limit=BIG)

    data = {
        "profiles": [_row(p.id, p.agent_name, p.description) for p in profiles],
        "skills": [_row(s.id, s.skill_name, s.description) for s in skills],
        "tools": [_row(t.id, t.tool_name, t.description) for t in tools],
        "packs": [_row(p.id, p.name, p.description) for p in packs],
    }
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print({k: len(v) for k, v in data.items()}, "->", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "catalog.real.json"))
    asyncio.run(main(ap.parse_args().out))
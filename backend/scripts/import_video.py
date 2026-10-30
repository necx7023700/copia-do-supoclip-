"""
Import a local video file directly into SupoClip and trigger background processing.

Usage inside supoclip-backend or supoclip-worker container:
    python scripts/import_video.py /app/uploads/my_video.mp4 --title "My Title" --format vertical
"""
import argparse
import asyncio
import hashlib
import os
import shutil
import uuid
from pathlib import Path
from sqlalchemy import text

from src.database import AsyncSessionLocal
from src.config import get_config
from src.services.task_service import TaskService
from src.services.video_service import VideoService
from src.workers.job_queue import JobQueue


async def import_video(
    file_path: str,
    title: str | None = None,
    output_format: str = "vertical",
    clip_length: str = "auto",
    user_id: str | None = None,
):
    source_path = Path(file_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Arquivo nao encontrado: {source_path}")

    config = get_config()
    uploads_dir = Path(config.temp_dir) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    extension = source_path.suffix or ".mp4"
    unique_filename = f"{uuid.uuid4()}{extension}"
    target_path = uploads_dir / unique_filename

    # If the file is already inside uploads_dir, we can rename/link or copy
    if source_path.parent.resolve() == uploads_dir.resolve():
        print(f"-> Renomeando para identificador unico: {target_path.name}")
        shutil.move(str(source_path), str(target_path))
    else:
        print(f"-> Copiando {source_path.name} para {target_path}...")
        shutil.copy2(str(source_path), str(target_path))

    print("-> Calculando tamanho e hash SHA256...")
    hasher = hashlib.sha256()
    size = target_path.stat().st_size
    with open(target_path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            hasher.update(chunk)
    digest = hasher.hexdigest()

    async with AsyncSessionLocal() as db:
        if not user_id:
            result = await db.execute(
                text("SELECT id, email FROM users ORDER BY created_at ASC LIMIT 1")
            )
            user_row = result.first()
            if not user_row:
                raise RuntimeError("Nenhum usuario encontrado no banco de dados!")
            user_id = str(user_row[0])
            user_email = str(user_row[1])
            print(f"-> Atribuindo ao usuario: {user_email} (ID: {user_id})")

        video_path = f"upload://{unique_filename}"
        session_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO media_upload_sessions (id, user_id, size, content_sha256, video_path, state)
                VALUES (:id, :user_id, :size, :digest, :video_path, 'completed')
            """),
            {
                "id": session_id,
                "user_id": user_id,
                "size": size,
                "digest": digest,
                "video_path": video_path,
            },
        )
        await db.commit()

        video_title = title or source_path.stem
        video_service = VideoService()
        duration = video_service._get_file_duration(target_path)
        duration_sec = int(duration) if duration else None
        print(
            f"-> Duracao do video: {duration_sec}s (~{int(duration_sec // 60) if duration_sec else 0} min)"
        )

        task_service = TaskService(db, config)
        task_id = await task_service.create_task_with_source(
            user_id=user_id,
            url=video_path,
            title=video_title,
            processing_mode="fast",
            source_duration_seconds=duration_sec,
        )

        job_id = await JobQueue.enqueue_processing_job(
            "process_video_task",
            "fast",
            task_id,
            video_path,
            "upload",
            user_id,
            output_format=output_format,
            processing_mode="fast",
            clip_length=clip_length,
            add_subtitles=True,
        )

        app_url = os.getenv("NEXT_PUBLIC_APP_URL", "http://187.41.96.205:3107").rstrip("/")
        print("\n" + "=" * 60)
        print("  SUCESSO: O VIDEO FOI IMPORTADO E ESTA SENDO PROCESSADO!")
        print("=" * 60)
        print(f"  Task ID : {task_id}")
        print(f"  Job ID  : {job_id}")
        print(f"  Painel  : {app_url}/tasks/{task_id}")
        print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Importar video local diretamente para o SupoClip"
    )
    parser.add_argument("file_path", help="Caminho do arquivo de video")
    parser.add_argument("--title", default=None, help="Titulo do video")
    parser.add_argument(
        "--format",
        default="vertical",
        choices=["vertical", "original", "square"],
        help="Formato de saida (padrao: vertical)",
    )
    parser.add_argument(
        "--clip-length",
        default="auto",
        help="Duracao dos clipes: auto, 30-60, 60-90, 90-180 (padrao: auto)",
    )
    parser.add_argument("--user-id", default=None, help="ID do usuario (opcional)")
    args = parser.parse_args()

    asyncio.run(
        import_video(
            file_path=args.file_path,
            title=args.title,
            output_format=args.format,
            clip_length=args.clip_length,
            user_id=args.user_id,
        )
    )


if __name__ == "__main__":
    main()

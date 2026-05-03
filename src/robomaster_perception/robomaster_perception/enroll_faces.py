import argparse
from pathlib import Path

import cv2
import numpy as np
from insightface.app import FaceAnalysis


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def largest_face(faces):
    if not faces:
        return None
    return max(
        faces,
        key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]),
    )


def create_face_app(model_name, det_size, use_gpu):
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if use_gpu else ["CPUExecutionProvider"]
    app = FaceAnalysis(name=model_name, providers=providers)
    app.prepare(ctx_id=0 if use_gpu else -1, det_size=det_size)
    return app


def normalize(vec):
    vec = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm <= 1e-6:
        return vec
    return vec / norm


def enroll(image_dir, output_file, model_name, det_size, use_gpu):
    image_dir = Path(image_dir).expanduser()
    output_file = Path(output_file).expanduser()

    app = create_face_app(model_name, det_size, use_gpu)
    names = []
    embeddings = []

    for person_dir in sorted(path for path in image_dir.iterdir() if path.is_dir()):
        person_embeddings = []
        for image_path in sorted(person_dir.iterdir()):
            if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            img = cv2.imread(str(image_path))
            if img is None:
                print(f"SKIP unreadable: {image_path}")
                continue
            face = largest_face(app.get(img))
            if face is None:
                print(f"SKIP no face: {image_path}")
                continue
            person_embeddings.append(normalize(face.normed_embedding))
            print(f"OK {person_dir.name}: {image_path.name}")

        if not person_embeddings:
            print(f"WARN no usable face images for {person_dir.name}")
            continue

        names.append(person_dir.name)
        embeddings.append(normalize(np.mean(person_embeddings, axis=0)))
        print(f"ENROLLED {person_dir.name}: {len(person_embeddings)} image(s)")

    if not names:
        raise RuntimeError(f"No identities enrolled from {image_dir}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_file,
        names=np.asarray(names),
        embeddings=np.asarray(embeddings, dtype=np.float32),
    )
    print(f"Saved {len(names)} identity/identities to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Build a RoboMaster face embedding database")
    parser.add_argument(
        "--image-dir",
        default="face_db/images",
        help="Folder containing one subfolder per identity",
    )
    parser.add_argument(
        "--output",
        default="face_db/embeddings/face_db.npz",
        help="Output .npz embedding database",
    )
    parser.add_argument("--model-name", default="buffalo_l")
    parser.add_argument("--det-size", type=int, nargs=2, default=(640, 640))
    parser.add_argument("--use-gpu", action="store_true", help="Request CUDAExecutionProvider for InsightFace")
    args = parser.parse_args()
    enroll(args.image_dir, args.output, args.model_name, tuple(args.det_size), args.use_gpu)


if __name__ == "__main__":
    main()

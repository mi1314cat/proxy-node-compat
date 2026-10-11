#!/usr/bin/env python3
"""Phase 0 reconcile: RN deployed files vs repo HEAD (+ full history).

Classifies each mapped pair:
  SAME          content identical to repo HEAD
  DIFFERS-OLD   content matches SOME historical version of that path (stale deploy)
  LOCAL-CHANGE  content matches NO version in history (hand-edited on RN) -> DO NOT OVERWRITE
  RN-ONLY       deployed file has no counterpart at the mapped repo path
  REPO-ONLY     repo HEAD file not present on RN
"""
import hashlib
import os
import subprocess
import sys
from collections import defaultdict

REPOS = {
    "xray": "/root/deepseek/repos/xray--core",
    "mihomo": "/root/deepseek/repos/mihomo--core",
    "singbox": "/root/deepseek/repos/sing-box-core",
}


def sh(args, cwd=None, binary=False):
    r = subprocess.run(args, cwd=cwd, capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Repo:
    def __init__(self, name, path, ref="HEAD"):
        self.name = name
        self.path = path
        self.ref = ref
        self.head = sh(["git", "rev-parse", ref], cwd=path).strip()
        self._head_cache = {}
        self._hist_cache = {}

    def head_sha(self, rel):
        if rel not in self._head_cache:
            b = sh(["git", "show", f"{self.ref}:{rel}"], cwd=self.path, binary=True)
            self._head_cache[rel] = None if b is None else sha256_bytes(b)
        return self._head_cache[rel]

    def head_blob(self, rel):
        return sh(["git", "show", f"{self.ref}:{rel}"], cwd=self.path, binary=True)

    def hist_shas(self, rel):
        """All distinct content sha256 ever recorded for this path, all refs."""
        if rel in self._hist_cache:
            return self._hist_cache[rel]
        out = sh(["git", "log", "--all", "--format=%H", "--", rel], cwd=self.path)
        commits = [c for c in (out or "").split() if c]
        shas = set()
        for c in commits:
            b = sh(["git", "show", f"{c}:{rel}"], cwd=self.path, binary=True)
            if b is not None:
                shas.add(sha256_bytes(b))
        self._hist_cache[rel] = shas
        return shas

    def head_files(self, subdir=""):
        args = ["git", "ls-tree", "-r", "--name-only", self.ref]
        if subdir:
            args.append(subdir)
        out = sh(args, cwd=self.path)
        return [l for l in (out or "").splitlines() if l]

    def first_seen(self, rel, target_sha):
        """Which commit first introduced this exact content (for stale reporting)."""
        out = sh(["git", "log", "--all", "--format=%H", "--", rel], cwd=self.path)
        commits = [c for c in (out or "").split() if c]
        for c in reversed(commits):
            b = sh(["git", "show", f"{c}:{rel}"], cwd=self.path, binary=True)
            if b is not None and sha256_bytes(b) == target_sha:
                subj = sh(["git", "log", "-1", "--format=%h %ci %s", c], cwd=self.path).strip()
                return subj, c
        return None, None


def load_manifest(path):
    rows = []
    with open(path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 5:
                continue
            label, sha, size, mtime, rpath = parts
            rows.append(dict(label=label, sha=sha, size=int(size),
                             mtime=float(mtime), rnpath=rpath))
    return rows


# ---------------------------------------------------------------- mappings
# RN path -> (repo, repo-relative path)  ; None = derived/runtime file
def map_x(rnpath, repo):
    if rnpath == "/root/xray-panel.sh":
        return "xray-panel.sh"
    # /root/catmi/xray/conf/*.json  -> runtime node configs (no repo counterpart)
    # /root/catmi/xray/out/*        -> generated share artifacts
    return None


def map_m(rnpath, repo):
    if rnpath.startswith("/root/catmi/mihomo/src/"):
        return "src/" + rnpath[len("/root/catmi/mihomo/src/"):]
    return None


def map_sb(rnpath, repo):
    if rnpath.startswith("/root/catmi/sing-box/conf/"):
        return "src/conf/" + rnpath[len("/root/catmi/sing-box/conf/"):]
    if rnpath == "/root/catmi/sing-box/install.sh":
        return "install.sh"
    if rnpath == "/root/catmi/sing-box/sing-box.sh":
        return "src/sing-box.sh"
    return None


# Pinned commits — HEAD was observed to move during this session (another agent
# was committing). Everything below reconciles against these exact commits.
PINNED = {
    "xray": "55c736afaaab6aafd59f34b7e99d7688ca5087b3",
    "mihomo": "54672782a1c06d962ac498d372c81672b0d9f5e9",
    "singbox": "2c209b0e017c26838bc7af5ba42849c0d341dd8c",
}

MAPPERS = {"xray": map_x, "mihomo": map_m, "singbox": map_sb}
# repo subtree that is expected to be deployed, per kernel
DEPLOY_SUBTREE = {"xray": "", "mihomo": "src", "singbox": "src/conf"}

# files that are legitimately on RN but never in the repo (runtime/byproduct)
RUNTIME_PREFIX = (
    "/root/catmi/xray/out/", "/root/catmi/xray/conf/", "/root/catmi/xray/share",
    "/root/catmi/mihomo/out/", "/root/catmi/mihomo/share", "/root/catmi/mihomo/scripts",
    "/root/catmi/sing-box/out/", "/root/catmi/sing-box/config/", "/root/catmi/sing-box/share",
    "/etc/systemd/system/",
)

LABEL2KERNEL = {"X-": "xray", "M-": "mihomo", "SB-": "singbox"}


def main():
    rows = load_manifest("/root/deepseek/repos/proxy-node-compat/research/deploy/evidence/rn-manifest.tsv")
    repos = {k: Repo(k, v, PINNED.get(k, "HEAD")) for k, v in REPOS.items()}
    report = {}
    for k, r in repos.items():
        print(f"[{k}] HEAD={r.head}", file=sys.stderr)

    by_kernel = defaultdict(lambda: dict(same=[], differs_old=[], local_change=[],
                                         rn_only=[], repo_only=[], runtime=[]))
    seen_repo = defaultdict(set)

    for row in rows:
        rnpath = row["rnpath"]
        kernel = None
        for pre, k in LABEL2KERNEL.items():
            if row["label"].startswith(pre):
                kernel = k
                break
        if kernel is None:
            continue
        repo = repos[kernel]
        rel = MAPPERS[kernel](rnpath, repo)
        if rel is None:
            if rnpath.startswith(RUNTIME_PREFIX):
                by_kernel[kernel]["runtime"].append(row)
            else:
                by_kernel[kernel]["rn_only"].append((rnpath, row, None))
            continue
        seen_repo[kernel].add(rel)
        hsha = repo.head_sha(rel)
        if hsha is None:
            by_kernel[kernel]["rn_only"].append((rnpath, row, rel))
            continue
        if hsha == row["sha"]:
            by_kernel[kernel]["same"].append((rnpath, rel, row))
        else:
            if row["sha"] in repo.hist_shas(rel):
                who, _ = repo.first_seen(rel, row["sha"])
                by_kernel[kernel]["differs_old"].append((rnpath, rel, row, who))
            else:
                by_kernel[kernel]["local_change"].append((rnpath, rel, row))

    # repo-only: HEAD files inside the deployed subtree with no RN counterpart
    for kernel, repo in repos.items():
        sub = DEPLOY_SUBTREE[kernel]
        for rel in repo.head_files(sub):
            if not rel.endswith((".sh", ".py", ".txt", ".json", ".md")):
                continue
            if rel in seen_repo[kernel]:
                continue
            if kernel == "xray" and not rel.startswith("conf/"):
                continue
            by_kernel[kernel]["repo_only"].append(rel)

    for kernel in ("xray", "mihomo", "singbox"):
        d = by_kernel[kernel]
        print(f"\n{'='*78}\n### {kernel}  (repo HEAD {repos[kernel].head[:8]})\n{'='*78}")
        print(f"  SAME          : {len(d['same'])}")
        print(f"  DIFFERS(stale): {len(d['differs_old'])}")
        print(f"  LOCAL-CHANGE  : {len(d['local_change'])}")
        print(f"  RN-ONLY       : {len(d['rn_only'])}")
        print(f"  REPO-ONLY     : {len(d['repo_only'])}")
        print(f"  runtime/derived (informational): {len(d['runtime'])}")

        if d["differs_old"]:
            print(f"\n  --- DIFFERS from HEAD, but matches an OLD repo version (stale deploy) ---")
            for rnpath, rel, row, who in sorted(d["differs_old"]):
                print(f"    {rel}")
                print(f"       RN : {rnpath}  sha={row['sha'][:16]}")
                print(f"       HEAD:{repos[kernel].head_sha(rel)[:16]}")
                print(f"       RN content == {who}")

        if d["local_change"]:
            print(f"\n  --- LOCAL CHANGE (matches NO version in history) — DO NOT OVERWRITE ---")
            for rnpath, rel, row in sorted(d["local_change"]):
                print(f"    {rel}")
                print(f"       RN : {rnpath}  sha={row['sha'][:16]}  size={row['size']}")
                print(f"       HEAD:{repos[kernel].head_sha(rel)[:16]}")

        if d["rn_only"]:
            print(f"\n  --- RN-ONLY (no counterpart at mapped repo path) ---")
            for rnpath, row, rel in sorted(d["rn_only"]):
                print(f"    {rnpath}   sha={row['sha'][:16]} size={row['size']}")

        if d["repo_only"]:
            print(f"\n  --- REPO-ONLY (in HEAD's deployed subtree, absent on RN) ---")
            for rel in sorted(d["repo_only"]):
                print(f"    {rel}")


if __name__ == "__main__":
    main()

import os
import re
import sys
import subprocess
import shutil
from pathlib import Path
from urllib.parse import unquote

# --- [수정됨] Git 파일 목록 가져오기 (ls-files 방식) ---
def get_git_changed_files(root_dir):
    """
    'git ls-files'를 실행하여 변경되거나(M) 추가된(O) '.md' 파일 목록을
    절대 경로(Path 객체)로 반환합니다.
    """
    print("Git 상태를 확인하여 변경된 .md 파일을 찾습니다...")
    changed_files = []
    
    try:
        # --modified: 추적 중인 파일 중 수정된 것
        result_mod = subprocess.run(
            ['git', 'ls-files', '--modified', '--exclude-standard'],
            capture_output=True, text=True, encoding='utf-8', check=True, cwd=root_dir
        )
        # --others: 추적 안 된 파일 (새 파일)
        result_new = subprocess.run(
            ['git', 'ls-files', '--others', '--exclude-standard'],
            capture_output=True, text=True, encoding='utf-8', check=True, cwd=root_dir
        )
        
        # 두 결과(수정된 파일 + 새 파일)를 합침
        all_files_str = result_mod.stdout + '\n' + result_new.stdout
        
        for file_path_str in all_files_str.strip().split('\n'):
            if not file_path_str:
                continue
            
            # .md 파일만 필터링
            if file_path_str.endswith('.md'):
                # ls-files는 항상 / 슬래시를 사용 (Pathlib이 OS에 맞게 처리)
                abs_path = root_dir / file_path_str
                
                # 이 스크립트 자체는 제외
                if abs_path.name == Path(__file__).name:
                    continue
                    
                changed_files.append(abs_path)

        if changed_files:
            print(f"✅ {len(changed_files)}개의 변경된 .md 파일을 찾았습니다.")
            for f in changed_files:
                # Path.relative_to는 OS에 맞게 (윈도우: \ ) 출력함
                print(f"   - {f.relative_to(root_dir)}") 
        else:
            print("✅ 변경된 .md 파일이 없습니다.")
            
        return changed_files

    except Exception as e:
        print(f"  ❌ Git 상태 확인 중 오류: {e}")
        return []

# --- get_next_image_index 함수 (수정 없음) ---
def get_next_image_index(post_image_dir):
    """
    'assets/img/posts/파일명/' 폴더를 스캔하여 '숫자.확장자' 형식의
    파일을 찾아 가장 큰 숫자를 찾고, 그 다음 숫자를 반환합니다.
    """
    max_index = 0
    pattern = re.compile(r"^(\d+)\..*$")

    if not post_image_dir.exists():
        post_image_dir.mkdir(parents=True, exist_ok=True)
        return 1

    for f in post_image_dir.glob("*.*"):
        match = pattern.match(f.name)
        if match:
            num = int(match.group(1))
            if num > max_index:
                max_index = num
                
    return max_index + 1

# --- process_markdown_file 함수 (수정 없음) ---
def process_markdown_file(md_file_path, root_dir):
    """
    단일 마크다운 파일을 처리하여 로컬 이미지를 정해진 경로로 이동시키고
    파일 내용을 업데이트합니다.
    """
    print(f"\n📄 '{md_file_path.relative_to(root_dir)}' 파일 처리 시작...")

    try:
        with open(md_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  ❌ 파일 읽기 오류: {e}")
        return

    base_file_name = md_file_path.stem 
    post_image_dir = root_dir / "assets" / "img" / "posts" / base_file_name

    image_pattern = re.compile(
        r'!\[([^\]]*)\]\((?!(?:https?://|images/|../images/|assets/img/posts/|/assets/img/posts/))([^)]+)\)'
    )
    
    matches = list(image_pattern.finditer(content))
    if not matches:
        print("  - 처리할 *새로운* Notion 로컬 이미지가 없습니다. 건너뜁니다.")
        return

    print(f"  - 총 {len(matches)}개의 새로운 Notion 로컬 이미지를 발견했습니다.")
    
    image_counter = get_next_image_index(post_image_dir)
    print(f"  - 이미지는 '{post_image_dir.relative_to(root_dir)}' 폴더에 {image_counter}번부터 저장됩니다.")
    
    new_content = content
    processed_count = 0
    empty_dirs_to_check = set()

    for match in reversed(matches):
        try:
            alt_text = match.group(1)
            original_local_path_encoded = match.group(2).strip()
            original_local_path_str = unquote(original_local_path_encoded)
            src_image_path = md_file_path.parent / original_local_path_str

            if not src_image_path.exists():
                src_image_path = md_file_path.parent / base_file_name / original_local_path_str
                if not src_image_path.exists():
                    print(f"    ⚠️ 원본 로컬 파일을 찾을 수 없습니다: {original_local_path_str}")
                    continue
            
            file_ext = src_image_path.suffix
            new_image_name = f"{image_counter}{file_ext}"
            dest_image_path = post_image_dir / new_image_name
            md_path = "/" + dest_image_path.relative_to(root_dir).as_posix()
            
            new_markdown_tag = f"![{alt_text}]({md_path})"
            
            shutil.move(src_image_path, dest_image_path)
            
            start, end = match.span()
            new_content = new_content[:start] + new_markdown_tag + new_content[end:]
            
            print(f"    ✅ '{original_local_path_str}' -> '{md_path}'로 이동 및 교체 완료.")
            
            empty_dirs_to_check.add(src_image_path.parent)
            processed_count += 1
            image_counter += 1 

        except Exception as e:
            print(f"    ❌ [처리 단계] 오류 발생: {e} (원본 경로: {original_local_path_str})")

    if processed_count > 0:
        try:
            with open(md_file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"  ✨ '{md_file_path.name}' 파일 업데이트 완료! (총 {processed_count}개 이미지 처리)")
        except Exception as e:
            print(f"  ❌ 파일 쓰기 오류: {e}")

    for folder in empty_dirs_to_check:
        try:
            if (folder.exists() and 
                folder.is_dir() and 
                not any(folder.iterdir()) and
                folder.parent == md_file_path.parent):
                
                folder.rmdir()
                print(f"  🗑️ 빈 폴더 삭제 완료: {folder.relative_to(root_dir)}")
        except OSError as e:
            print(f"  ⚠️ 폴더 삭제 실패: {folder.name} ({e})")

# --- 메인 실행 로직 (수정 없음) ---
def main():
    root_directory = Path.cwd() 

    if not (root_directory / ".git").is_dir():
        print(f"❌ 이 스크립트는 Git 저장소의 루트 폴더에서 실행해야 합니다.")
        sys.exit(1)
        
    posts_dir_abs = root_directory / "_posts"

    changed_md_files = get_git_changed_files(root_directory)
    
    if not changed_md_files:
        print("\n처리할 마크다운 파일이 없습니다. (모든 파일이 최신 상태입니다)")
        return

    processed_count = 0
    for md_file in changed_md_files:
        if posts_dir_abs not in md_file.parents:
            print(f"\n📄 '{md_file.relative_to(root_directory)}' 파일은 '_posts/' 폴더 안이 아니므로 건너뜁니다.")
            continue
        
        if md_file.name.lower() == 'readme.md':
            print(f"\n📄 '{md_file.relative_to(root_directory)}' 파일은 건너뜁니다 (README).")
            continue

        process_markdown_file(md_file, root_directory)
        processed_count += 1

    if processed_count == 0:
         print("\nℹ️ 변경된 파일 중 '_posts' 폴더 내의 파일이 없어 처리를 건너뛰었습니다.")
        
    print("\n🎉 모든 작업이 완료되었습니다!")

if __name__ == "__main__":
    main()
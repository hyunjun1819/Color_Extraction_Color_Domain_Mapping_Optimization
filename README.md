# Color Extraction-based Color Domain Mapping Optimization

이미지에서 대표 색상을 추출하고, 각 색상을 미리 정의한 컬러 도메인에 매핑하는 Python 프로그램입니다. RGB 색상을 CIE Lab으로 변환한 뒤 CIEDE2000 색차를 계산하여 가장 가까운 색상명과 그룹을 찾습니다.

현재 기본 컬러 도메인은 170개 색상명과 24개 색상 그룹으로 구성되어 있습니다.

## 주요 기능

- 투명 픽셀과 배경으로 간주한 검정 픽셀 제외
- Gray World와 저채도 중립색을 이용한 조명·색편향 보정
- Pillow 양자화와 `extcolors`를 이용한 대표 RGB 추출
- 픽셀 빈도를 반영한 대표 색상 클러스터링
- CIE Lab(D65, 2° 관찰자) 및 CIEDE2000 기반 컬러 도메인 매핑
- 무채색 계열에 대한 BLACK, GREY, WHITE 그룹 우선 판정
- 색상 그룹 비율, 매칭된 색상명, 색차를 JSON으로 출력

## 프로젝트 구조

```text
.
├── ciede_color_extractor/
│   ├── __main__.py          # 명령행 인터페이스
│   ├── preprocessing.py     # 픽셀 필터링과 색상 보정
│   ├── clustering.py        # 대표 색상 추출과 클러스터링
│   ├── ciede2000.py         # RGB-Lab 변환과 CIEDE2000 계산
│   └── extractor.py         # 컬러 도메인 로딩과 최종 분석
├── configs/
│   └── color_domain.json    # 색상명, RGB, 그룹 정의
├── src/utils/
│   └── color_extractor.py   # 호환용 import 경로
└── requirements.txt
```

## 설치

저장소를 받은 뒤 프로젝트 루트에서 가상 환경을 만들고 의존성을 설치합니다.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS 또는 Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 사용법

### 명령행 실행

```bash
python -m ciede_color_extractor path/to/image.jpg
```

분석할 이미지 경로만 지정하면 기본 컬러 도메인인 `configs/color_domain.json`을 사용합니다. 결과는 표준 출력에 JSON으로 표시됩니다.

주요 옵션은 다음과 같습니다.

| 옵션 | 기본값 | 설명 |
| --- | ---: | --- |
| `--domain` | `configs/color_domain.json` | 사용할 컬러 도메인 JSON 경로 |
| `--clusters` | `20` | 생성할 최대 RGB 클러스터 수 |
| `--tolerance` | `10.0` | 대표 색상을 묶을 때 사용하는 RGB 거리 허용치 |
| `--top` | `3` | 반환할 상위 색상 그룹 수 |
| `--alpha-threshold` | `0` | 이 값 이하의 알파 채널을 가진 픽셀 제외 |
| `--include-black` | 사용 안 함 | 순수 검정 픽셀을 분석 대상에 포함 |
| `--no-color-correction` | 사용 안 함 | 조명 및 중립색 기반 보정 비활성화 |
| `--neutral-saturation-threshold` | `0.25` | 중립색 후보를 고르는 채도 상한 |

예를 들어 상위 5개 그룹을 확인하고 색상 보정을 끄려면 다음과 같이 실행합니다.

```bash
python -m ciede_color_extractor sample.png --top 5 --no-color-correction
```

출력에는 그룹별 비율과 각 클러스터의 상세 매칭 결과가 함께 포함됩니다.

```json
{
  "method": "CIEDE2000",
  "color_space": "CIE Lab (D65/2-degree)",
  "domain_color_count": 170,
  "visible_pixel_count": 5000,
  "cluster_count": 2,
  "top_groups": [
    {
      "color": "BLUE",
      "percentage": 60.0
    }
  ],
  "clusters": [
    {
      "rgb": [40, 90, 160],
      "pixel_count": 3000,
      "percentage": 60.0,
      "matched_color": "MediumDenim",
      "group": "BLUE",
      "delta_e_2000": 0.0,
      "neutral_priority_group": null
    }
  ]
}
```

위 예시는 출력 구조를 간단히 보여주기 위해 일부 항목과 배열 원소를 생략한 형태입니다.

### Python 코드에서 사용

```python
from PIL import Image

from ciede_color_extractor import ColorExtractor


extractor = ColorExtractor("configs/color_domain.json")

with Image.open("sample.png") as image:
    report = extractor.analyze(image, top_n=3)

print(report["top_groups"])
```

상위 그룹만 필요하면 `extract_colors()`를 사용할 수 있습니다.

```python
with Image.open("sample.png") as image:
    colors = extractor.extract_colors(image, top_n=3)
```

## 컬러 도메인 수정

`configs/color_domain.json`은 색상명을 키로 사용하며, 각 항목에 기준 RGB와 그룹을 지정합니다.

```json
{
  "CobaltBlue": {
    "rgb": [0, 71, 171],
    "group": "BLUE"
  },
  "NavyBlue": {
    "rgb": [0, 0, 124],
    "group": "NAVY"
  }
}
```

RGB 채널 값은 각각 0부터 255 사이의 정수여야 합니다. 그룹명은 로딩 과정에서 앞뒤 공백이 제거되고 대문자로 정규화됩니다.

## 처리 과정

1. 이미지의 알파 채널을 확인하고 제외 대상 픽셀을 제거합니다.
2. 전체 픽셀의 채널 평균과 충분히 밝은 저채도 픽셀을 이용해 색상 보정 게인을 계산합니다.
3. 보정된 픽셀을 제한된 팔레트로 양자화하고 대표 RGB를 추출합니다.
4. 픽셀 빈도를 가중치로 사용하여 가까운 RGB를 클러스터로 합칩니다.
5. 각 클러스터를 CIE Lab으로 변환하고 컬러 도메인 전체와 CIEDE2000 색차를 비교합니다.
6. 매칭된 그룹별 픽셀 비율을 집계하여 상위 그룹과 상세 결과를 반환합니다.

색상 보정은 촬영 환경의 색편향을 줄이기 위한 일반적인 보정입니다. 카메라 프로파일이나 표준 컬러 차트를 사용하는 계측 수준의 색상 보정을 대신하지는 않습니다.

## 참고 문헌

G. Sharma, W. Wu, E. N. Dalal, “The CIEDE2000 Color-Difference Formula: Implementation Notes, Supplementary Test Data, and Mathematical Observations,” *Color Research & Application*, 30(1), 21–30, 2005. [https://doi.org/10.1002/col.20070](https://doi.org/10.1002/col.20070)

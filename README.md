# ProView — STL Viewer with Cut & Alignment tools

<div dir="rtl">

## ProView — عارض ملفات STL مع أدوات القطع والمحاذاة

برنامج لويندوز لعرض ملفات STL (مثل نماذج الأسنان والقوالب)، يحتوي على:

### 1. أداة القطع (Cut) — زر `X`
تعمل بطريقة مشابهة للقطع في exocad: تحدد جزءًا من السطح ثم تحذفه.

| الطريقة | الاستخدام |
|---|---|
| **فرشاة** `B` | اسحب بالزر الأيسر للتلوين على الجزء المراد قطعه. `Ctrl` + العجلة أو `[` `]` لتغيير الحجم |
| **لاسو** `L` | ارسم بالماوس شكلًا حرًا حول الجزء |
| **نقاط موصولة** `P` | انقر لتثبيت نقاط متصلة بخط. أغلق المسار بالنقر على النقطة الأولى (الخضراء) أو بنقر مزدوج أو `Enter`. يمكنك تدوير النموذج بين النقرات. `Backspace` يحذف آخر نقطة |

- اضغط **`Delete`** في الكيبورد أو زر **حذف المحدد** لحذف الجزء المحدد.
- `Ctrl` + أي طريقة تحديد = إلغاء تحديد.
- التحديد يشمل الأوجه الظاهرة فقط، ويمكن تفعيل **قطع نافذ** لقطع الجزء الخلفي أيضًا.
- أدوات إضافية: إبقاء المحدد فقط، عكس التحديد، توسيع/تقليص التحديد، حذف الأجزاء الصغيرة المنفصلة.
- `Ctrl+Z` للتراجع.

### 2. أداة المحاذاة (Alignment) — زر `A`
اختر **النموذج الثابت** و**النموذج المتحرك** (Floating) ثم:
- **اختيار أزواج النقاط**: تنقسم الشاشة (يسار = الثابت، يمين = المتحرك). انقر على 3 نقاط متطابقة أو أكثر وبنفس الترتيب على النموذجين، ثم **محاذاة بالنقاط** (مع تحسين تلقائي بأفضل تطابق).
- **Best-fit**: تحسين المحاذاة من الوضع الحالي (ICP).
- **Auto alignment**: محاذاة تلقائية بدون نقاط.
- **محاذاة كل النماذج الظاهرة** على النموذج الثابت دفعة واحدة.

بعد الانتهاء احفظ النموذج من **ملف ← حفظ النموذج باسم** (يتم حفظ الوضع الجديد بعد المحاذاة والقطع)، أو صدّر كل النماذج كملف واحد.

### التحكم بالعرض
الزر الأيمن: تدوير — الزر الأوسط: تحريك — العجلة: تكبير/تصغير — `F`: ملاءمة الكل. يمكن سحب ملفات STL وإفلاتها داخل البرنامج. اللغة (عربي / English) من قائمة **عرض ← اللغة**.

### التشغيل على ويندوز
- **نسخة جاهزة (exe):** من تبويب **Actions** في GitHub افتح آخر تشغيل لـ *Build Windows* وحمّل `ProView-windows.zip`، فك الضغط وشغّل `ProView.exe`.
- **من الكود المصدري:** ثبّت Python 3.10+ ثم شغّل `run_windows.bat`.
- **بناء exe بنفسك:** شغّل `build_windows.bat` والناتج في `dist\ProView\ProView.exe`.

</div>

---

## English

A Windows desktop STL viewer (Python, Qt/PySide6, VTK) with:

**Cut tool (`X`)** — exocad-style region cutting. Select with a **brush** (`B`), **freehand lasso** (`L`) or **connected points** (`P`, click points on the model, close on the first point / double-click / Enter; you can rotate between clicks). Delete with the **Delete key** or the button. Ctrl inverts the action (deselect). Only visible faces are selected unless *Cut through* is enabled. Also: keep selection, invert, grow/shrink, remove small loose parts, undo (`Ctrl+Z`).

**Alignment tool (`A`)** — choose a fixed and a floating model, then:
- **Point pairs** in a split view (left fixed, right floating), ≥ 3 pairs → Kabsch alignment, optionally refined by best-fit.
- **Best-fit** — trimmed point-to-plane ICP from the current pose.
- **Auto alignment** — global search (current pose, centroid match and 24 principal-axis orientations, each refined by ICP), no points needed.
- **Auto-align all visible models** to the fixed one.

Saving writes binary STL with the model's current pose applied. Non-ASCII (e.g. Arabic) file paths are supported.

### Run / build
```bat
run_windows.bat      :: run from source (creates .venv, installs requirements)
build_windows.bat    :: builds dist\ProView\ProView.exe with PyInstaller
```
The GitHub Actions workflow `.github/workflows/build-windows.yml` builds the Windows executable on every push and uploads `ProView-windows.zip` as an artifact (and attaches it to a release when a `v*` tag is pushed).

### Development
```bash
pip install -r requirements.txt pytest
python -m pytest tests
python main.py model1.stl model2.stl
```

| Module | Purpose |
|---|---|
| `proview/mesh.py` | Mesh data, fast numpy STL read/write, components, VTK conversion |
| `proview/alignment.py` | Kabsch, point-to-plane ICP, auto alignment |
| `proview/selection.py` | Screen projection, z-buffer visibility, lasso/brush tests, ray picking |
| `proview/cut_tool.py` | Cut tool interaction + panel |
| `proview/align_tool.py` | Alignment interaction (split view picking) + panel |
| `proview/viewer.py` | VTK view in Qt, tool-aware interactor style |
| `proview/app.py` | Main window, model list, undo, menus |

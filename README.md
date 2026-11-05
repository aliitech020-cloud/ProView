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

### المقطع (Section) — زر `S`
ارسم خطًا بالماوس عبر النماذج في العرض ثلاثي الأبعاد، فيُقطع العرض على امتداد هذا الخط (للعرض فقط، لا يتغير الملف).
تظهر لوحة ثنائية الأبعاد فيها خطوط المقطع لكل نموذج:
- انقر نقطتين لقياس المسافة (تلتصق بالخطوط).
- اختر **المرجع** و**المقارن** لعرض الفرق بين نموذجين بعد المحاذاة: يُلوَّن الخط بالأخضر/الأصفر/الأحمر حسب حجم الفرق، ويظهر أقصى فرق ومتوسطه وموضعه.
- شريط **Move** لتحريك المقطع، و **Flip side** لعكس الجهة المخفية.

### 3. الدمج (Merge) — زر `M`
حدد نموذجين أو أكثر في القائمة (Ctrl + نقر) ثم اضغط **Merge**، فيتم إنشاء نموذج واحد جديد وتُخفى النماذج الأصلية. إذا لم تحدد شيئًا يتم دمج كل النماذج الظاهرة.

يدعم البرنامج ملفات **STL** و **PLY** للفتح والحفظ. بعد الانتهاء احفظ النموذج من **File ← Save model as** (يتم حفظ الوضع الجديد بعد المحاذاة والقطع).

### التحكم بالعرض
الزر الأيمن: تدوير — الزر الأوسط: تحريك — العجلة: تكبير/تصغير — `F`: ملاءمة الكل. يمكن سحب ملفات STL وإفلاتها داخل البرنامج.

### الواجهة
- لوحة النماذج عائمة دائمًا فوق العرض (اسحبها من عنوانها). لكل نموذج: زر إظهار/إخفاء، دائرة اللون (انقر لتغييره)، وشريط شفافية خاص به بلون النموذج.
- مكعب الاتجاهات أعلى اليمين: انقر على أي وجه (TOP / FRONT / RIGHT ...) للانتقال إليه بحركة سلسة. المفاتيح `1`-`6` و `0` للمنظور.
- ألوان ملفات PLY (ألوان المسح) تظهر تلقائيًا، ويمكن إخفاؤها بزر **Colors** أو `C`. عند الحفظ بصيغة PLY تُحفظ الألوان.

### التشغيل على ويندوز
- **مثبّت (Setup):** من Actions حمّل `ProView-Setup` وشغّله؛ يضيف البرنامج لقائمة ابدأ وسطح المكتب ويمكن إلغاء تثبيته من إعدادات ويندوز.
- **نسخة محمولة (Portable):** حمّل `ProView-portable` وفك الضغط وشغّل `ProView.exe` بدون تثبيت.
- **من الكود المصدري:** ثبّت Python 3.10+ ثم شغّل `run_windows.bat`.
- **بناء exe بنفسك:** شغّل `build_windows.bat` والناتج في `dist\ProView\ProView.exe`.

</div>

---

## English

A Windows desktop STL viewer (Python, Qt/PySide6, VTK) with:

**Cut tool (`X`)** — exocad-style region cutting. Select with a **brush** (`B`), **freehand lasso** (`L`) or **connected points** (`P`, click points on the model, close on the first point / double-click / Enter; you can rotate between clicks). Delete with the **Delete key** or the button. Ctrl inverts the action (deselect). Only visible faces are selected unless *Cut through* is enabled. Also: keep selection, invert, grow/shrink, remove small loose parts, undo (`Ctrl+Z`).

**Section view (`S`)** — drag a line across the models to slice the view (display only). A 2D panel shows each model's section curve; click two points to measure, and pick a reference and compared model to colour the compared curve by gap (green/yellow/red thresholds) with max/mean gap and the max location marked. Move the plane with the slider, flip the hidden side.

**Merge (`M`)** — Ctrl/Shift-click several models in the list and press Merge to combine them into one new model (originals are hidden). With no multi-selection, all visible models are merged.

**File formats** — open and save **STL** and **PLY** (ASCII and binary).

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

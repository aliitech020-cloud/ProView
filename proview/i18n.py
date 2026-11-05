"""Very small English / Arabic translation table."""
from __future__ import annotations

LANG = "en"

_STRINGS = {
    "app_title": ("ProView - STL Viewer", "ProView - عارض ملفات STL"),
    # menus
    "menu_file": ("&File", "&ملف"),
    "menu_edit": ("&Edit", "&تحرير"),
    "menu_view": ("&View", "&عرض"),
    "menu_tools": ("&Tools", "&أدوات"),
    "menu_help": ("&Help", "&مساعدة"),
    "menu_language": ("Language", "اللغة"),
    "open": ("Open model (STL / PLY)...", "فتح نموذج (STL / PLY)..."),
    "save": ("Save model as...", "حفظ النموذج باسم..."),
    "save_merged": ("Export visible models merged...", "تصدير النماذج الظاهرة كملف واحد..."),
    "exit": ("Exit", "خروج"),
    "undo": ("Undo", "تراجع"),
    "reset_view": ("Fit all", "ملاءمة الكل"),
    "view_front": ("Front", "أمامي"),
    "view_back": ("Back", "خلفي"),
    "view_left": ("Left", "يسار"),
    "view_right": ("Right", "يمين"),
    "view_top": ("Top", "علوي"),
    "view_bottom": ("Bottom", "سفلي"),
    "view_iso": ("Isometric", "منظور"),
    "scan_colors": ("Show scan colors (PLY)", "إظهار ألوان المسح"),
    "scan_colors_row": ("Show this model's scan colors", "إظهار ألوان هذا النموذج"),
    "toggle_visible": ("Show / hide", "إظهار / إخفاء"),
    "drag_panel": ("Drag to move the panel", "اسحب لتحريك اللوحة"),
    "tool_section": ("Section view", "مقطع"),
    "tile_section": ("Section", "مقطع"),
    "section_title": ("Section view", "عرض المقطع"),
    "section_help": ("Drag a line across the models in the 3D view (left mouse). The models are sliced "
                     "along that line for viewing only - nothing is changed. Right drag still rotates.",
                     "ارسم خطًا عبر النماذج في العرض ثلاثي الأبعاد."),
    "section_offset": ("Move", "تحريك"),
    "section_clip": ("Hide one side", "إخفاء جهة"),
    "section_flip": ("Flip side", "عكس الجهة"),
    "section_clear": ("Clear", "مسح"),
    "section_none": ("No section yet - drag a line in the 3D view.", "لا يوجد مقطع بعد."),
    "section_view_help": ("Click two points to measure (snaps to the curves). Wheel = zoom, right drag = pan, "
                          "double-click = fit. Hover the colored curve to read the gap.",
                          "انقر نقطتين للقياس. العجلة للتكبير، الزر الأيمن للتحريك."),
    "gap_reference": ("Reference", "المرجع"),
    "gap_compared": ("Compared", "المقارن"),
    "gap_limits": ("Gap colors", "ألوان الفرق"),
    "gap_choose": ("Choose a reference and a compared model to see the gap.", "اختر نموذجين لعرض الفرق."),
    "gap_stats": ("Gap along this section:  max {max:.3f} mm  |  mean {mean:.3f} mm",
                  "الفرق في هذا المقطع: الأقصى {max:.3f} مم | المتوسط {mean:.3f} مم"),
    "flat_view": ("Flat (sharp) shading", "عرض حاد"),
    "tile_flat": ("Flat", "حاد"),
    "tool_orient": ("Orientation", "الاتجاه"),
    "tile_orient": ("Orient", "اتجاه"),
    "orient_title": ("Orientation", "تعديل الاتجاه"),
    "orient_help": ("Drag a colored ring to rotate the model around that axis, or an arrow to move it "
                    "(hold Shift for fine steps). Drag elsewhere to turn the camera. The blue plane is "
                    "horizontal (the XY plane) - use it to level the model. Changes are kept when you save.",
                    "اسحب الحلقات للتدوير والأسهم للتحريك."),
    "orient_model": ("Model: {name}", "النموذج: {name}"),
    "orient_plane": ("Show horizontal reference plane", "إظهار المستوي المرجعي"),
    "orient_step": ("Step", "الخطوة"),
    "orient_rotate_axis": ("Rotate {axis}", "تدوير {axis}"),
    "orient_drop": ("Place model on the plane", "وضع النموذج على المستوي"),
    "orient_cancel": ("Cancel changes", "إلغاء التغييرات"),
    "orient_cancel_tip": ("Back to the orientation the model had when you opened this tool",
                          "العودة للاتجاه عند فتح الأداة"),
    "orient_reset": ("Reset to original", "العودة للأصل"),
    "orient_reset_tip": ("Back to the orientation stored in the file (undoes alignment too)",
                         "العودة لاتجاه الملف الأصلي"),
    "material": ("Material", "المادة"),
    "custom_color": ("Custom color...", "لون مخصص..."),
    "tile_cut": ("Cut", "قطع"),
    "tile_align": ("Align", "محاذاة"),
    "tile_merge": ("Merge", "دمج"),
    "tile_colors": ("Colors", "ألوان"),
    "tile_edges": ("Edges", "حواف"),
    "tile_fit": ("Fit", "ملاءمة"),
    "wireframe": ("Show edges", "إظهار الحواف"),
    "parallel": ("Orthographic projection", "إسقاط متعامد"),
    "tool_cut": ("Cut", "قطع"),
    "tool_align": ("Alignment", "محاذاة"),
    "shortcuts": ("Shortcuts", "اختصارات"),
    "about": ("About", "حول"),
    "restart_lang": ("The language will change after restarting the program.", "سيتم تغيير اللغة بعد إعادة تشغيل البرنامج."),
    # model panel
    "models": ("Models", "النماذج"),
    "color": ("Color", "اللون"),
    "opacity": ("Opacity", "الشفافية"),
    "remove_model": ("Remove", "إزالة"),
    "no_model": ("No model selected", "لا يوجد نموذج محدد"),
    "info": ("{faces:,} triangles  |  {verts:,} vertices\nSize: {sx:.2f} x {sy:.2f} x {sz:.2f}",
             "{faces:,} مثلث  |  {verts:,} نقطة\nالأبعاد: {sx:.2f} x {sy:.2f} x {sz:.2f}"),
    "confirm_remove": ("Remove model \"{name}\" from the scene?", "إزالة النموذج \"{name}\" من المشهد؟"),
    # cut tool
    "cut_title": ("Cut tool", "أداة القطع"),
    "cut_mode": ("Selection mode", "طريقة التحديد"),
    "mode_brush": ("Brush", "فرشاة"),
    "mode_lasso": ("Lasso (freehand)", "لاسو (رسم حر)"),
    "mode_polygon": ("Points (polyline)", "نقاط موصولة"),
    "brush_size": ("Brush size", "حجم الفرشاة"),
    "through": ("Cut through (include hidden faces)", "قطع نافذ (يشمل الأوجه المخفية)"),
    "delete_sel": ("Delete selection  [Del]", "حذف المحدد  [Del]"),
    "keep_sel": ("Keep only selection", "إبقاء المحدد فقط"),
    "invert_sel": ("Invert selection", "عكس التحديد"),
    "clear_sel": ("Clear selection  [Esc]", "إلغاء التحديد  [Esc]"),
    "grow_sel": ("Grow", "توسيع"),
    "shrink_sel": ("Shrink", "تقليص"),
    "remove_islands": ("Remove small loose parts", "حذف الأجزاء الصغيرة المنفصلة"),
    "selected_count": ("Selected: {n:,} triangles", "المحدد: {n:,} مثلث"),
    "cut_help": (
        "Left mouse: select   |   Ctrl + left: deselect\n"
        "Right drag: rotate   |   Middle drag: pan   |   Wheel: zoom\n"
        "Points mode: click points, close by clicking the first point,\n"
        "double-click or Enter. Backspace removes the last point.\n"
        "Brush: Ctrl + wheel or [ ] changes the size.",
        "زر الماوس الأيسر: تحديد   |   Ctrl + أيسر: إلغاء تحديد\n"
        "سحب بالزر الأيمن: تدوير   |   الزر الأوسط: تحريك   |   العجلة: تكبير\n"
        "وضع النقاط: انقر لإضافة نقاط، وأغلق المسار بالنقر على النقطة الأولى\n"
        "أو بالنقر المزدوج أو Enter. Backspace يحذف آخر نقطة.\n"
        "الفرشاة: Ctrl + العجلة أو [ ] لتغيير الحجم."),
    "select_model_first": ("Select a model in the list first.", "اختر نموذجًا من القائمة أولاً."),
    # align tool
    "align_title": ("Alignment", "المحاذاة"),
    "fixed_model": ("Fixed model", "النموذج الثابت"),
    "floating_model": ("Floating model", "النموذج المتحرك"),
    "pick_points": ("Pick point pairs (split view)", "اختيار أزواج النقاط (عرض مقسوم)"),
    "pick_help": (
        "Left view = fixed, right view = floating.\n"
        "Click matching points in the same order on both models (at least 3).\n"
        "Right drag rotates each view, left drag also rotates.",
        "العرض الأيسر = الثابت، العرض الأيمن = المتحرك.\n"
        "انقر على نقاط متطابقة وبنفس الترتيب على النموذجين (3 نقاط على الأقل).\n"
        "السحب بالزر الأيمن أو الأيسر يدوّر كل عرض."),
    "points_status": ("Fixed points: {a}   |   Floating points: {b}", "نقاط الثابت: {a}   |   نقاط المتحرك: {b}"),
    "undo_point": ("Remove last point", "حذف آخر نقطة"),
    "clear_points": ("Clear points", "مسح النقاط"),
    "align_points": ("Align by points", "محاذاة بالنقاط"),
    "refine": ("Refine with best-fit after point alignment", "تحسين بأفضل تطابق بعد المحاذاة بالنقاط"),
    "best_fit": ("Best-fit alignment", "محاذاة أفضل تطابق (Best-fit)"),
    "auto_align": ("Auto alignment", "محاذاة تلقائية (Auto)"),
    "auto_all": ("Auto-align all visible models to fixed", "محاذاة كل النماذج الظاهرة تلقائيًا على الثابت"),
    "iterations": ("Iterations", "عدد التكرارات"),
    "need_pairs": ("Pick at least 3 point pairs (same count on both models).",
                   "اختر 3 أزواج نقاط على الأقل (نفس العدد على النموذجين)."),
    "need_two": ("Choose two different models (fixed and floating).", "اختر نموذجين مختلفين (ثابت ومتحرك)."),
    "align_result": ("Done: RMS = {rms:.4f}  |  overlap = {frac:.0%}", "تم: RMS = {rms:.4f}  |  التطابق = {frac:.0%}"),
    "working": ("Working...", "جاري العمل..."),
    # misc
    "loaded": ("Loaded {name} ({faces:,} triangles)", "تم تحميل {name} ({faces:,} مثلث)"),
    "saved": ("Saved {path}", "تم الحفظ: {path}"),
    "error": ("Error", "خطأ"),
    "load_failed": ("Could not open {path}:\n{err}", "تعذر فتح {path}:\n{err}"),
    "nothing_to_undo": ("Nothing to undo", "لا يوجد ما يمكن التراجع عنه"),
    "mesh_filter": ("3D models (*.stl *.ply);;STL files (*.stl);;PLY files (*.ply);;All files (*)",
                    "نماذج ثلاثية الأبعاد (*.stl *.ply);;STL (*.stl);;PLY (*.ply);;كل الملفات (*)"),
    "save_filter": ("STL file (*.stl);;PLY file (*.ply)", "ملف STL (*.stl);;ملف PLY (*.ply)"),
    "merge": ("Merge", "دمج"),
    "merge_tip": ("Merge the selected models (Ctrl/Shift+click in the list) into one model.\n"
                  "If fewer than two are selected, all visible models are merged.\n"
                  "The original models are hidden, not deleted.",
                  "دمج النماذج المحددة في نموذج واحد."),
    "merge_need": ("Select at least two models (Ctrl+click) or show at least two models to merge.",
                   "حدد نموذجين على الأقل للدمج."),
    "merge_done": ("Merged {n} models into one ({faces:,} triangles). The originals are hidden.",
                   "تم دمج {n} نماذج ({faces:,} مثلث)."),
    "models_tip": ("Ctrl/Shift + click to select several models (for Merge).", "Ctrl + نقر لتحديد عدة نماذج."),
    "drop_hint": ("Open or drag & drop STL / PLY files here", "افتح ملفات STL أو اسحبها وأفلتها هنا"),
    "shortcut_text": (
        "Ctrl+O  Open\nCtrl+S  Save model\nCtrl+Z  Undo\nX  Cut tool\nA  Alignment tool\nS  Section view (measure gaps)\nO  Orientation\nH  Flat (sharp) shading\nM  Merge models\nE  Show edges\nC  Scan colors\n"
        "1-6  Front / Back / Left / Right / Top / Bottom,  0  Isometric\nClick a face of the view cube to look at it\n"
        "B / L / P  Brush / Lasso / Points\nDel  Delete selection\nEsc  Cancel / clear selection\n"
        "Enter  Close points polyline\nBackspace  Remove last point\n[ ]  Brush size\nF  Fit all",
        "Ctrl+O  فتح\nCtrl+S  حفظ النموذج\nCtrl+Z  تراجع\nX  أداة القطع\nA  أداة المحاذاة\n"
        "B / L / P  فرشاة / لاسو / نقاط\nDel  حذف المحدد\nEsc  إلغاء / إلغاء التحديد\n"
        "Enter  إغلاق مسار النقاط\nBackspace  حذف آخر نقطة\n[ ]  حجم الفرشاة\nF  ملاءمة الكل"),
    "about_text": ("ProView {v}\nSTL viewer with cutting and alignment tools.",
                   "ProView {v}\nعارض ملفات STL مع أدوات القطع والمحاذاة."),
}


def set_language(lang: str) -> None:
    global LANG
    LANG = "ar" if lang == "ar" else "en"


def tr(key: str, **kw) -> str:
    pair = _STRINGS.get(key)
    if pair is None:
        return key
    text = pair[1] if LANG == "ar" else pair[0]
    return text.format(**kw) if kw else text

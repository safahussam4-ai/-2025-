// ---------------------------
// جامعة الحدباء الأهلية – نظام المشتريات
// وظائف تفاعلية بسيطة
// ---------------------------

// تنبيه ترحيبي عند تحميل الصفحة
document.addEventListener("DOMContentLoaded", function() {
    console.log("نظام المشتريات - جامعة الحدباء جاهز للعمل 💼");
});

// تلوين الصفوف بالتناوب في الجدول
function colorTableRows() {
    const rows = document.querySelectorAll("table tr");
    rows.forEach((row, index) => {
        if (index % 2 === 0) {
            row.style.backgroundColor = "#f9f9f9";
        }
    });
}

// تفعيل عند تحميل الصفحة
window.onload = colorTableRows;

// تأكيد قبل حذف أي عنصر
function confirmDelete(itemName) {
    return confirm("هل أنت متأكد من حذف " + itemName + "؟");
}

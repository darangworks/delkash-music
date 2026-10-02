# Content Model — Music Work vs Recordings

## هدف

هر صفحهٔ موسیقی یک اثر/Composition را معرفی می‌کند، اما ممکن است بیش از یک Recording داشته باشد؛ برای نمونه اجرای اصلی صفحه و بازخوانی.

این تفکیک دو مفهوم متفاوت را جدا می‌کند:
- **اثر:** عنوان، آهنگساز، ترانه‌سرا و دستگاه.
- **اجرا/ضبط:** خواننده/اجراکننده، فایل صوتی و نقش آن نسبت به اثر.

این مدل با رابطهٔ `MusicComposition.recordedAs` و `MusicRecording.recordingOf` در Schema.org هم‌راستا است.

## Front matter

فیلدهای قدیمی `artist` و `audio` فعلاً حفظ می‌شوند تا مهاجرت backward-compatible باشد. برای محتوای جدید، اطلاعات اجرا باید در `recordings` ثبت شود.

```yaml
alternateTitles:
  - "خدا کنه خوابم نبره"

recordings:
  - artist: "مرضیه"
    role: "primary"
    audio: "https://example.org/original.mp3"
  - artist: "جهان"
    role: "cover"
    audio: "https://example.org/cover.mp3"
```

### قرارداد `recordings`
- `artist`: نام اجراکننده.
- `role`: فقط `original` یا `cover`.
- `audio`: لینک مستقیم فایل صوتی.
- `duration`: اختیاری؛ در صورت وجود ISO 8601 مثل `PT5M11S`.
- سال ضبط، ناشر یا منبع فقط وقتی اضافه شوند که واقعاً مستند باشند.
- ترتیب آرایه همان ترتیب نمایش در صفحه است؛ معمولاً اجرای اصلی صفحه اول می‌آید.

### سازگاری با مدل قبلی
در مهاجرت فعلی `artist` و `audio` حذف نمی‌شوند؛ `recordings` مدل جدید است و رفتار فعلی پخش و URLها باید حفظ شود. حذف legacy fields به یک cleanup جداگانه پس از audit کامل موکول می‌شود.

## عنوان جایگزین
اگر یک اثر عنوان جایگزین مستند دارد، از `alternateTitles` استفاده شود. این عنوان نباید بدون نیاز محتوایی به taxonomy مستقل تبدیل شود.

## چرا این مدل؟
Schema.org، `MusicComposition` را برای خود اثر و `MusicRecording` را برای یک ضبط مشخص تعریف می‌کند؛ `recordedAs` از composition به recording و `recordingOf` رابطهٔ معکوس است. `MusicRecording.byArtist` نیز می‌تواند Person یا MusicGroup باشد.

## محدودیت‌های فعلی
تاریخ ضبط/انتشار، ناشر، ISRC، آلبوم و provenance فعلاً اجباری نیستند و فقط پس از audit منبع باید اضافه شوند.

## سیاست مهاجرت
1. URLهای فعلی حفظ شوند.
2. محتوای موجود بدون بازنویسی کامل migrate شود.
3. اول مدل داده و rendering پیاده شود.
4. سپس Schema.org به مدل جدید متصل شود.
5. legacy fields فقط پس از audit کامل حذف شوند.

# Hướng dẫn sử dụng Blue Archive Resource Scanner

App đọc những gì đang hiện trên màn hình game (tiền tệ, vật phẩm, trang bị, chỉ số học sinh) bằng ảnh chụp màn hình + OCR, lưu thành file JSON, rồi xuất sang các công cụ lập kế hoạch (Justin163 Planner, Schale DB, Midokuni).

Có hai cách scan:

| Nền tảng | Cách scan | App có bấm vào game không? |
|---|---|---|
| **PC client (Steam)** | Read-only: bạn tự bấm trong game, app chỉ chụp và đọc | **Không bao giờ** |
| Emulator / điện thoại Android (ADB) | Tự động: app tự bấm qua các menu | Có (là macro) |

Hướng dẫn này đi theo bản **Steam**. Phần emulator nằm ở [mục 10](#10-emulator--điện-thoại-scan-tự-động).

**Toàn bộ quy trình:** cài app → chỉnh game → Settings → kiểm tra vùng đọc → scan → export.

---

## 1. Chuẩn bị

- Windows 10 hoặc 11.
- Một trong hai: [uv](https://docs.astral.sh/uv/) hoặc Python 3.13 trở lên (khi cài Python nhớ tick *Add python.exe to PATH*).
- Blue Archive bản Steam, đã đăng nhập và vào được sảnh (lobby).

## 2. Mở app

Double-click **`run.bat`** trong thư mục app.

- Lần đầu, nó tự cài các gói Python (mất vài phút). Nếu báo thiếu Python thì cài theo link nó in ra rồi chạy lại.
- Sau đó hiện menu:

| Phím | Chức năng |
|---|---|
| `1` | Scan tự động — chỉ cho emulator / điện thoại |
| `2` | **Read-only scan — dùng cho bản Steam** |
| `3` | Settings: chọn nền tảng |
| `4` | Check layout: kiểm tra vùng đọc có khớp màn hình không |
| `5` | Export sang Justin163 Planner |
| `6` | Export sang Schale DB |
| `7` | Export link roster Midokuni |
| `8` | Update data: tải dữ liệu vật phẩm / học sinh mới nhất |
| `0` | Thoát |

Gõ số rồi Enter. Sau mỗi chức năng, bấm phím bất kỳ để quay lại menu.

## 3. Chỉnh trong game (bắt buộc)

Vào Options của game và đặt:

| Tuỳ chọn | Giá trị | Lý do |
|---|---|---|
| Language | **English** | App chỉ đọc được tên trang và tên vật phẩm tiếng Anh |
| Screen Ratio | **16:9** | Vùng đọc được đo theo khung 16:9 |
| Screen Mode | Window hoặc Fullscreen | Kích thước nào cũng được, miễn khung game tối thiểu **1280x720** |
| Display Shortcut Icons | **Off** | Các nhãn phím tắt che mất chữ cần đọc |

Thêm:

- Tắt thông báo của Steam overlay khi scan (chúng vẽ đè lên hình game).
- Không thu nhỏ (minimize) cửa sổ game trong lúc scan. Nên để cửa sổ game nằm trên cùng.
- Màn hình không phải 16:9 (laptop 16:10, ultrawide) vẫn dùng được: game tự thêm viền đen, app tự bỏ viền.

## 4. Settings — mục `3` (làm một lần)

Chọn `3`, cửa sổ Settings mở ra:

1. **Step 1 - Setup:** chọn **PC client / desktop window**. Ô *Game window title* giữ nguyên `Blue Archive`.
2. **Step 2 - Scan Targets:** chỉ ảnh hưởng tới scan tự động. Với bản Steam cứ để nguyên.
3. **Step 3, Step 4:** để mặc định.
4. Bấm **Save Settings**.

Cài đặt được lưu vào `config/settings.json`. Mục `2` và `4` sẽ không chạy nếu chưa làm bước này.

## 5. Check layout — mục `4` (nên làm lần đầu)

Bước này xác nhận app nhìn đúng chỗ trên màn hình của bạn. Làm lại khi đổi độ phân giải hoặc màn hình.

1. Mở game, đứng ở sảnh.
2. Chọn `4`.
3. Trong game, tự mở một màn hình; trong cửa sổ app, gõ tên màn hình đó rồi Enter:
   `home` (sảnh), `menu`, `equipment`, `items`, `students` (danh sách), `student` (trang chi tiết một học sinh).
4. Gõ `q` để thoát.
5. Mở thư mục `output\layout\`, xem các file `*_overlay.png`: **các khung xanh phải nằm đúng trên chữ / số**. Nếu lệch, kiểm tra lại mục 3 (nhất là Screen Ratio 16:9).

## 6. Scan — mục `2` Read-only scan

App không bấm gì cả. Bạn tự đi trong game, app chụp màn hình liên tục và giữ lại những gì bạn đã xem.

### 6.1. Bắt đầu

Chọn `2`, Enter để xác nhận. Khi thấy dòng **`Watching the game, nothing is clicked.`** thì chuyển sang game.

### 6.2. Đi qua các màn hình trong game

Thứ tự tuỳ ý, không cần làm hết trong một lần. Mỗi khi vào một màn hình app nhận ra, cửa sổ app in `On Lobby`, `On Equipment`, `On Items` hoặc `On Student`.

| Muốn đọc | Làm gì trong game | App in ra |
|---|---|---|
| **AP, Credits, Pyroxene** | Đứng ở sảnh 1–2 giây, không để popup che thanh trên cùng | `On Lobby` |
| **Equipment** | Sảnh → Menu → Equipment. Bấm **từng ô một**, giữ mỗi ô khoảng **1 giây** cho bảng chi tiết hiện ổn định. Tự cuộn xuống để xem hết | `Equipment: N captured` |
| **Items** | Sảnh → Menu → Items. Làm y như Equipment | `Items: N captured` |
| **Students** | Sảnh → Students → mở học sinh đầu tiên → bấm **mũi tên sang học sinh kế tiếp**, khoảng **1 giây** mỗi học sinh | `Student: N captured` |

Mẹo:

- Nhìn số `N captured` tăng lên để biết ô / học sinh vừa rồi đã được ghi nhận. Không tăng thì giữ lâu hơn một chút.
- Xem lại một ô đã xem cũng không sao, kết quả không bị nhân đôi.
- Lần đầu nên thử ít: xem 3–4 item và 2 học sinh, kết thúc, kiểm tra file kết quả (mục 7) rồi mới scan toàn bộ.

### 6.3. Kết thúc

Bấm **F2**. Nếu F2 không có tác dụng khi đang ở trong game, chuyển sang cửa sổ app và bấm **Ctrl+C**.

App in `Reading what was captured...`, chạy OCR, lưu kết quả và in `Done.`. Số lượng nhiều thì bước này mất một lúc — đừng đóng cửa sổ.

### 6.4. Kết quả được gộp như thế nào

- Kết quả **gộp** vào lần scan trước: item / học sinh bạn không xem lần này **giữ nguyên giá trị cũ**.
- Vì vậy item đã dùng hết (không còn trong túi để bấm vào) vẫn giữ số cũ. Muốn làm lại từ đầu thì xoá `output\owned\scanned_items.json` hoặc `scanned_equipment.json` rồi scan lại.

## 7. File kết quả

Tất cả nằm trong thư mục `output\`:

| File | Nội dung |
|---|---|
| `owned\scanned_currencies.json` | AP, Credits, Pyroxene |
| `owned\scanned_equipment.json`, `owned\scanned_items.json` | Tên và số lượng thô đọc được |
| `owned\scanned_students.json` | Chỉ số thô của học sinh |
| `equipment_final_values.json`, `items_final_values.json`, `students_final_values.json` | Dữ liệu đã khớp với ID, các exporter đọc từ đây |

Mỗi học sinh được đọc: tên, level, bond, số sao, tier 3 trang bị + bond gear, sao và level của vũ khí riêng (UE), 4 kỹ năng, 3 chỉ số talent.

OCR có thể đọc sai. Nên liếc qua vài giá trị quan trọng trước khi export.

## 8. Export

Chạy sau khi đã scan. Cả ba đều chạy trên máy, không gửi dữ liệu tài khoản đi đâu.

### 8.1. Justin163 Planner — mục `5`

1. (Nên làm) Để giữ dữ liệu sẵn có trong planner: vào justin163.com/planner, export, lưu thành `input\justin_data.json`.
2. Chọn `5`. Ở dòng *Options* gõ Enter, hoặc:
   - `-m` — đặt mục tiêu MAX cho học sinh mới thêm.
   - `-o` — tải dữ liệu mới nhất trước khi xuất.
3. Import file `output\justin_data_final.json` vào planner.

### 8.2. Schale DB — mục `6`

> **Cẩn thận:** *Import Collection* của Schale DB **thay thế toàn bộ** collection. Học sinh không có trong file import sẽ bị xoá.

1. Để giữ những học sinh chưa scan: trên schaledb.com → Settings → **Export Collection**, lưu đoạn text vào một file.
2. Chọn `6`. Kéo-thả file đó vào cửa sổ app khi được hỏi (hoặc Enter để bỏ qua).
3. *Options*: Enter, hoặc `-l` (khoá tất cả), `-o` (tải dữ liệu mới trước).
4. Mở `output\SchaleDB_import.txt`, copy toàn bộ nội dung → schaledb.com → Settings → **Import Collection** → dán → Import.

### 8.3. Midokuni — mục `7`

1. Chọn `7`. *Options*: Enter, hoặc `-s blue` / `-s black` (đặt trạng thái cho mọi học sinh), `-o`.
2. App in ra **Full Roster URL** — mở link đó trong trình duyệt. Link cũng được lưu ở `output\midokuni_roster.json`.

## 9. Update data — mục `8`

Tải danh sách vật phẩm / trang bị / học sinh mới nhất từ kho cộng đồng BA-Scanner-Data trên GitHub. Chạy khi game ra học sinh hoặc vật phẩm mới, hoặc khi export báo `unmatched` / `N/A`. Sau khi cập nhật, scan lại những học sinh / item bị thiếu để chúng được khớp lại.

## 10. Emulator / điện thoại (scan tự động)

Chỉ dùng cho emulator hoặc Android qua ADB. Đây là macro: app tự bấm qua các menu.

1. Emulator đặt độ phân giải **1280x720**, bật ADB.
2. Mục `3` Settings → chọn **Emulator**, nhập ADB port (MuMu: `16384`, LDPlayer / BlueStacks: `5555`) → tick các mục cần scan ở *Scan Targets* → Save.
3. Mở game ở sảnh, chọn `1`. Bấm **F2** để dừng; các màn hình đã xong vẫn được lưu.

Trên PC client, mục `1` sẽ từ chối chạy và chỉ sang mục `2` — đây là chủ ý.

## 11. Lỗi thường gặp

| Thông báo / hiện tượng | Cách xử lý |
|---|---|
| `No settings yet: choose [3] Settings first` | Làm mục 4 |
| `Window 'Blue Archive' not found. Is the game running?` | Mở game. Tiêu đề cửa sổ phải đúng `Blue Archive` |
| `Game area is ..., smaller than the 1280x720 minimum` | Phóng to cửa sổ hoặc dùng fullscreen; app tự chạy tiếp khi đủ lớn |
| `... (not 16:9) and the picture is not letterboxed` | Đặt Screen Ratio = 16:9 trong game |
| `is minimized` / `is not in front` lặp lại | Mở lại cửa sổ game, đưa nó lên trên cùng |
| Không thấy `On Equipment` / `On Student` khi đã vào đúng màn hình | Game chưa để English, hoặc vùng đọc lệch → chạy mục `4` |
| Số `captured` không tăng | Giữ mỗi ô / học sinh lâu hơn (khoảng 1 giây) |
| `OCR could not read any ...` | Như trên: kiểm tra ngôn ngữ và mục `4` |
| `Skipping unmatched student` / giá trị `N/A` | Chạy mục `8`, rồi scan lại học sinh đó |
| `Can't use the settings, fix or delete the file` | Xoá `config\settings.json`, làm lại mục 4 |
| `The automatic scan clicks through the game...` | Bạn chọn mục `1` trên PC client → dùng mục `2` |

## 12. Về an toàn tài khoản

- Trên PC client, app **không có code** bấm chuột, kéo, gõ phím vào game hay focus cửa sổ game. Nó không đọc bộ nhớ, không chèn code, không chặn mạng, không đụng file game. Nó chỉ chụp cửa sổ game bằng API chụp màn hình của Windows, giống phần mềm quay màn hình.
- Phím F2 được nghe bằng một bộ lắng nghe bàn phím toàn hệ thống: chỉ nghe, không gửi phím nào.
- Bản Steam có anti-cheat (Nexon Game Security) và Nexon cấm macro / công cụ tự động. App tránh hoàn toàn phần đó trên PC, nhưng đây vẫn là công cụ không chính thức: không ai cam kết được Nexon cho phép. Bạn tự cân nhắc khi dùng.

## Phụ lục: chạy bằng lệnh

Trong thư mục app, sau khi đã kích hoạt môi trường ảo (`.venv\Scripts\activate`):

```bash
python -m gui.run              # Settings
python -m tools.capture_layout # Check layout
python -m tools.manual_scan    # Read-only scan (PC client)
python launch.py               # Scan tự động (emulator / điện thoại)
python -m tools.justin_planner [-m] [-o] [-f đường_dẫn]
python -m tools.schaledb [-l] [-o] [-f đường_dẫn]
python -m tools.midokuni [-s blue|black] [-o]
python -m tools.sync_data      # Update data
```

# แผนพัฒนา AutoCAD MCP Server (Python)

เอกสารนี้เขียนเพื่อส่งต่อให้ Claude Code ลงมือเขียนโค้ด ให้ทำตามลำดับ Milestone และหยุดรอตรวจทุกครั้งที่จบ Milestone

## 1. เป้าหมาย

สร้าง MCP server ด้วย Python ที่ให้ Claude (Claude Desktop / Claude Code) สั่งงาน AutoCAD 2022 ที่เปิดอยู่บนเครื่อง Windows ผ่าน COM automation ได้ เพื่อ

1. อ่านข้อมูลจาก drawing (layer, object, พื้นที่, ข้อความ)
2. วาด object พื้นฐาน (line, polyline, circle, text, rectangle) พร้อมกำหนด layer
3. วางผังแผงโซลาร์เซลล์ (solar panel layout) ในขอบเขต polyline ที่กำหนด พร้อมสรุปจำนวนแผงและ kWp
4. บันทึก / export ไฟล์ (DWG, DXF, PDF)

ผู้ใช้สื่อสารกับ Claude เป็นภาษาไทย ชื่อ tool, พารามิเตอร์ และ comment ในโค้ดใช้ภาษาอังกฤษ ข้อความที่ส่งกลับให้ผู้ใช้อ่านใช้ภาษาอังกฤษสั้นๆ แล้ว Claude จะแปลเอง

## 2. สภาพแวดล้อมและข้อจำกัด

- OS: Windows (AutoCAD 2022 ลงบนเครื่องนี้) ต้องเปิด AutoCAD ค้างไว้ และมี drawing เปิดอยู่
- Python 3.10 ขึ้นไป
- Library: `mcp` (Python SDK, ใช้ `FastMCP`), `pywin32` (COM), `shapely` (คำนวณ geometry), `pytest`
- Transport: stdio (ให้ Claude Desktop เป็นผู้เปิด process)
- **ห้าม `print()` ลง stdout** เพราะ stdout ใช้สื่อสาร MCP ให้ log ไป stderr หรือไฟล์เท่านั้น
- AutoCAD COM ไม่ thread-safe: เรียก COM จาก thread เดียว (ใช้ tool แบบ sync หรือ lock) และเรียก `pythoncom.CoInitialize()` ถ้าใช้ thread แยก
- ถ้า AutoCAD ติด dialog ค้างหรือกำลังรันคำสั่ง COM จะ error `RPC_E_CALL_REJECTED` ให้ทำ retry พร้อม backoff สั้นๆ (เช่น 5 ครั้ง ครั้งละ 0.5 วินาที)

## 3. โครงสร้างโปรเจกต์

```
autocad-mcp/
├─ pyproject.toml
├─ README.md
├─ src/autocad_mcp/
│  ├─ __init__.py
│  ├─ server.py          # FastMCP app, ลงทะเบียน tool
│  ├─ cad.py             # ชั้นครอบ COM (connect, retry, helper แปลง point)
│  ├─ tools_read.py      # tool อ่านข้อมูล
│  ├─ tools_draw.py      # tool วาด
│  ├─ tools_file.py      # tool save/export
│  ├─ solar/
│  │  ├─ layout.py       # อัลกอริทึมวางแผง (shapely ล้วน ไม่ยุ่งกับ COM)
│  │  ├─ spacing.py      # คำนวณระยะระหว่างแถว
│  │  └─ tools_solar.py  # tool ฝั่ง MCP ที่เรียก layout + วาดลง CAD
│  └─ config.py          # ค่าเริ่มต้น เช่น layer name, safe mode
└─ tests/
   ├─ test_layout.py     # ทดสอบอัลกอริทึมได้โดยไม่ต้องมี AutoCAD
   └─ test_cad_mock.py   # ทดสอบ tool ด้วย mock ของ COM
```

หลักการ: แยก "logic" (solar/layout.py) ออกจาก "COM" (cad.py) เพื่อทดสอบ logic ได้โดยไม่ต้องเปิด AutoCAD

## 4. ชั้นครอบ COM (cad.py)

ต้องมีฟังก์ชันเหล่านี้

- `get_app()` : `win32com.client.GetActiveObject("AutoCAD.Application")` ถ้าไม่เจอให้ raise error ชัดเจนว่า "AutoCAD is not running"
- `get_doc()` : `app.ActiveDocument` และ `get_modelspace()` : `doc.ModelSpace`
- `to_point(x, y, z=0)` : คืน VARIANT `pythoncom.VT_ARRAY | pythoncom.VT_R8` ขนาด 3 ค่า (COM ของ AutoCAD ต้องการ array ของ double ไม่ใช่ tuple ธรรมดา)
- `to_flat_2d(points)` : แปลงลิสต์ (x, y) เป็น array แบน `[x1,y1,x2,y2,...]` สำหรับ `AddLightWeightPolyline`
- `ensure_layer(name, color=None)` : สร้าง layer ถ้ายังไม่มี (`doc.Layers.Add`) และคืนชื่อ
- `with_retry(fn)` : retry เมื่อเจอ `RPC_E_CALL_REJECTED`
- `undo_group()` : context manager ที่ใช้ `doc.StartUndoMark()` / `EndUndoMark()` เพื่อให้ผู้ใช้กด Undo ครั้งเดียวย้อนทั้ง tool call ได้ (ตรวจสอบว่า method นี้มีใน 2022 ถ้าไม่มีให้ fallback เป็นไม่ทำ undo group)

ทุก object ที่สร้างให้คืน `Handle` (string) เพื่อให้ Claude อ้างอิงต่อได้

## 5. รายการ Tool (MCP)

### 5.1 กลุ่มอ่านข้อมูล (read-only ปลอดภัย)

| Tool | พารามิเตอร์ | ผลลัพธ์ |
|---|---|---|
| `get_drawing_info` | - | ชื่อไฟล์, path, unit (INSUNITS), จำนวน object ใน ModelSpace |
| `list_layers` | - | รายชื่อ layer, สี, on/off, locked |
| `list_objects` | `layer?`, `type?`, `limit=200` | handle, type, layer, bounding box ของแต่ละ object |
| `get_polyline` | `handle` | ลิสต์จุด (x, y), closed หรือไม่, พื้นที่, ความยาว |
| `get_text_in_layer` | `layer` | ข้อความและตำแหน่ง |

### 5.2 กลุ่มวาด (แก้ drawing ต้องใช้ undo group)

| Tool | พารามิเตอร์ | ผลลัพธ์ |
|---|---|---|
| `create_layer` | `name`, `color_index?` | ชื่อ layer |
| `draw_line` | `start`, `end`, `layer?` | handle |
| `draw_polyline` | `points`, `closed=false`, `layer?` | handle |
| `draw_rectangle` | `origin`, `width`, `height`, `rotation_deg=0`, `layer?` | handle |
| `draw_circle` | `center`, `radius`, `layer?` | handle |
| `add_text` | `position`, `text`, `height`, `layer?` | handle |
| `zoom_extents` | - | ok |

กฎความปลอดภัย: **ไม่ทำ tool ลบหรือแก้ object เดิมใน Milestone 1–3** ถ้าจำเป็นต้องมีภายหลัง ต้องมีพารามิเตอร์ `confirm=true` และ `dry_run=true` เป็นค่าเริ่มต้น

### 5.3 กลุ่มไฟล์

| Tool | พารามิเตอร์ | ผลลัพธ์ |
|---|---|---|
| `save_drawing` | - | บันทึกไฟล์ปัจจุบัน |
| `save_copy_as` | `path`, `format` (dwg/dxf) | บันทึกสำเนา ไม่เปลี่ยนไฟล์ที่เปิดอยู่ (ใช้ `SaveAs` กับสำเนา หรือ export) |
| `export_pdf` | `path` | export PDF ของ layout/model (ใช้ `doc.Plot` หรือ `-EXPORT` ผ่าน `SendCommand`) |

path ต้องอยู่ในโฟลเดอร์ที่ผู้ใช้อนุญาตเท่านั้น (ดูหัวข้อ 8)

### 5.4 กลุ่มแผงโซลาร์ (ส่วนเด่นของโปรเจกต์)

**`layout_solar_panels`**

พารามิเตอร์

- `boundary_handle` : handle ของ closed polyline ที่เป็นขอบพื้นที่ติดตั้ง (หรือส่ง `boundary_points` แทนได้)
- `obstacle_handles?` : ลิสต์ handle ของสิ่งกีดขวาง (closed polyline) เช่น ปล่องหรือกล่องเครื่อง
- `panel_length`, `panel_width` : ขนาดแผง หน่วยเดียวกับ drawing
- `panel_watt` : กำลังไฟต่อแผง (Wp)
- `orientation` : `portrait` | `landscape` | `auto` (auto = ลองทั้งสองแบบแล้วเลือกจำนวนแผงมากกว่า)
- `gap_x`, `gap_y` : ระยะเว้นระหว่างแผง
- `edge_setback` : ระยะเว้นจากขอบพื้นที่
- `obstacle_clearance` : ระยะเว้นรอบสิ่งกีดขวาง
- `rotation_deg=0` : หมุนกริดวางแผงตามแนวสันหลังคา (ถ้าไม่ระบุ ใช้มุมของขอบยาวที่สุดของ boundary)
- `unit_scale=1.0` : ตัวคูณแปลงหน่วยของ drawing (เช่น drawing เป็น mm แต่ผู้ใช้พูดเป็นเมตร)
- `dry_run=true` : ค่าเริ่มต้น **ไม่วาดลง drawing** แค่คำนวณและรายงาน

ผลลัพธ์ (JSON)

- `panel_count`, `total_kwp`, `orientation_used`
- `area_boundary`, `area_usable`, `coverage_ratio`
- `panel_origins` (ตัดให้สั้นถ้าเยอะ)
- ถ้า `dry_run=false`: `handles` ของ object ที่วาด (สี่เหลี่ยมแผงอยู่ layer `SOLAR_PANEL`, ข้อความสรุปอยู่ layer `SOLAR_TEXT`)

**`compute_row_spacing`** (สำหรับติดตั้งแบบเอียงบนพื้นราบ/ดาดฟ้า ไม่เกี่ยวกับ COM)

- พารามิเตอร์: `panel_length`, `tilt_deg`, `latitude_deg`, `design_hour_note?`
- สูตร: ความสูงด้านหลังแผง `h = L * sin(tilt)`, มุมดวงอาทิตย์ต่ำสุดตอนเที่ยงวันครีษมายันฤดูหนาว `alpha = 90 - |latitude| - 23.44` (องศา), ความยาวเงา `s = h / tan(alpha)`, ระยะ pitch ระหว่างแถว `pitch = L * cos(tilt) + s`
- คืนค่า `pitch`, `shadow_length`, `alpha_used` และหมายเหตุว่าเป็นค่าประมาณเบื้องต้น ต้องให้วิศวกรยืนยัน
- ตัวอย่างค่า latitude: เชียงใหม่ ประมาณ 18.8 องศา

**`summarize_string_sizing`** (เพิ่มภายหลังได้ใน Milestone 5)

- รับสเปกแผง (Voc, Vmp, Isc, Imp, temp coefficient) และสเปก inverter (max DC voltage, MPPT range, max current) คืนจำนวนแผงต่อ string ต่ำสุด/สูงสุด และเตือนถ้าเกินช่วง

## 6. อัลกอริทึมวางแผง (solar/layout.py)

ใช้ `shapely` ล้วน เป็นฟังก์ชัน pure ทดสอบได้ง่าย

1. สร้าง `Polygon` จาก boundary แล้วหัก `edge_setback` ด้วย `buffer(-edge_setback)` ถ้าผลว่างให้คืน 0 แผง
2. สร้างสิ่งกีดขวางเป็น polygon ขยายด้วย `buffer(+obstacle_clearance)` แล้ว `difference` ออกจากพื้นที่ใช้งาน
3. หมุนระบบพิกัดให้แนวกริดขนานกับ `rotation_deg` (ใช้ `shapely.affinity.rotate` รอบจุดศูนย์กลาง boundary ทำงานในพิกัดที่หมุนแล้วค่อยหมุนกลับตอนวาด)
4. กำหนดขนาดแผงตาม orientation (portrait: กว้าง = panel_width, สูง = panel_length ส่วน landscape สลับกัน)
5. วนกริดจาก bounding box ของพื้นที่ใช้งาน ระยะก้าวแนวนอน = ความกว้างแผง + `gap_x`, แนวตั้ง = ความสูงแผง + `gap_y`
6. แต่ละช่องสร้างสี่เหลี่ยมแผง ถ้า `usable.contains(rect)` ให้นับและเก็บ
7. ปรับ offset เริ่มต้นของกริด (เช่น ลองเลื่อน 0, ครึ่งหนึ่ง, ... ของขนาดช่อง เพียงไม่กี่แบบ) แล้วเลือกแบบที่ได้แผงมากสุด (ทำเป็นตัวเลือก `optimize_offset=true` ค่าเริ่มต้นเปิด)
8. ถ้า orientation เป็น `auto` ให้รันทั้ง portrait และ landscape แล้วเลือกอันที่ได้แผงมากกว่า
9. คืน `list[Polygon]` ของแผง จากนั้น tool ฝั่ง MCP ค่อยวาดลง CAD

ข้อจำกัดที่ต้องบอกผู้ใช้ในผลลัพธ์: อัลกอริทึมนี้เป็นแบบกริดสี่เหลี่ยม ไม่ได้หาค่าที่ดีที่สุดเชิงทฤษฎี ไม่คิดเงาจากอาคารข้างเคียง และไม่ทดแทนการออกแบบโดยวิศวกร

## 7. Milestones

**M0: เตรียมโปรเจกต์** (เสร็จเมื่อ `uv run` หรือ `python -m autocad_mcp.server` เริ่มได้โดยไม่ error)
- สร้างโครงสร้างตามหัวข้อ 3, `pyproject.toml`, README ฉบับสั้น
- ลง dependency, ตั้งค่า logging ไป stderr

**M1: เชื่อม AutoCAD และอ่านข้อมูล**
- ทำ `cad.py` และ tool กลุ่ม 5.1
- ทดสอบ: เปิด AutoCAD + drawing ตัวอย่าง แล้วเรียก `get_drawing_info` และ `list_layers` ได้ถูกต้อง
- ทำ test ด้วย mock COM ครอบคลุม retry และกรณี AutoCAD ไม่ได้เปิด

**M2: วาด object พื้นฐาน**
- tool กลุ่ม 5.2 ทั้งหมด พร้อม `undo_group`
- ทดสอบ: วาด polyline ปิดแล้วอ่านกลับด้วย `get_polyline` ได้พื้นที่ตรงกับที่คำนวณเอง

**M3: ชั้น logic วางแผง (ยังไม่ต่อ CAD)**
- ทำ `solar/layout.py` และ `solar/spacing.py` พร้อม `tests/test_layout.py`
- กรณีทดสอบขั้นต่ำ: สี่เหลี่ยมผืนผ้าที่คำนวณด้วยมือได้ (เช่น 10 x 6 ม. แผง 2.278 x 1.134 ม. gap 0.02 ม. setback 0.5 ม.), มีสิ่งกีดขวางตรงกลาง, พื้นที่รูปตัว L, setback ใหญ่จนไม่เหลือพื้นที่ (ต้องได้ 0 แผง ไม่ crash), orientation auto
- เปรียบเทียบผลกับการนับด้วยมือแล้วใส่ไว้เป็น expected value

**M4: ต่อ layout เข้ากับ CAD**
- `layout_solar_panels` ที่อ่าน boundary จาก handle, เรียก logic, วาดผลลง layer `SOLAR_PANEL` (เมื่อ `dry_run=false`) และเขียนข้อความสรุปลง `SOLAR_TEXT`
- ทดสอบกับ drawing จริงที่มีหลังคาสี่เหลี่ยมและหลังคามีสิ่งกีดขวาง

**M5: งานเสริม**
- `summarize_string_sizing`, `save_copy_as`, `export_pdf`
- ปรับปรุงข้อความ error ให้ชัด และเขียนคู่มือการติดตั้งใน README

## 8. ความปลอดภัยและ Safe mode

- ค่า `config.py` ต้องมี `ALLOWED_EXPORT_DIRS` (ลิสต์โฟลเดอร์ที่อนุญาตให้เขียนไฟล์) tool กลุ่มไฟล์ปฏิเสธ path นอกลิสต์นี้
- ห้ามใช้ `SendCommand` ส่งข้อความที่มาจาก input ของผู้ใช้โดยตรง ถ้าต้องใช้ให้สร้างคำสั่งจาก template ที่กำหนดเองเท่านั้น (กัน command injection)
- ตรวจ input ทุกตัว: ตัวเลขต้องเป็นบวกเมื่อควรเป็นบวก, จำนวนจุดไม่เกินขีดจำกัด (เช่น 10,000), จำนวนแผงที่วาดต่อครั้งไม่เกิน (เช่น 5,000) เพื่อกัน AutoCAD ค้าง
- ทุก tool ที่แก้ drawing ใส่อยู่ใน undo group เดียว
- error ที่ส่งกลับต้องไม่เปิดเผย path ภายในเครื่องเกินจำเป็น
- ใช้งานกับไฟล์สำเนาก่อนเสมอ ระบุไว้ใน README

## 9. การติดตั้งใช้งานกับ Claude Desktop (ใส่ใน README)

ตัวอย่างการตั้งค่า `claude_desktop_config.json` (ปรับ path ตามเครื่องจริง)

```json
{
  "mcpServers": {
    "autocad": {
      "command": "C:\\path\\to\\autocad-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "autocad_mcp.server"]
    }
  }
}
```

ถ้าใช้ Claude Code ให้เพิ่มด้วยคำสั่ง `claude mcp add autocad -- <python path> -m autocad_mcp.server`

## 10. เกณฑ์ว่าเสร็จ (Definition of Done)

- `pytest` ผ่านทั้งหมด โดยส่วนที่ไม่ต้องใช้ AutoCAD ต้องรันได้บนเครื่องไหนก็ได้
- ทดสอบมือบนเครื่องจริงผ่าน: เรียก tool จาก Claude Desktop แล้วเห็นผลใน AutoCAD 2022 ตาม Milestone 1, 2 และ 4
- `layout_solar_panels` ด้วย `dry_run=true` ไม่แก้ drawing เลย (ตรวจด้วยการนับ object ก่อนและหลัง)
- กดสั่ง Undo ใน AutoCAD ครั้งเดียวแล้วย้อนผลของ tool call หนึ่งครั้งได้
- README บอกวิธีติดตั้ง, ข้อจำกัด และคำเตือนว่าผลการออกแบบต้องให้วิศวกรตรวจ

## 11. ข้อควรระวังสำหรับ Claude Code

- ถ้าไม่แน่ใจเรื่อง API ของ AutoCAD COM เวอร์ชัน 2022 (เช่น `StartUndoMark`, การส่ง VARIANT array) ให้เขียนสคริปต์ทดสอบสั้นๆ แล้วถามผู้ใช้ให้รันบนเครื่องที่มี AutoCAD ก่อนสรุปว่าใช้ได้ อย่าเดา
- Claude Code ที่รันบน Linux/cloud ทดสอบ COM จริงไม่ได้ ให้เขียนและทดสอบ logic + mock ได้ แล้วระบุชัดว่าส่วน COM ยังไม่ผ่านการทดสอบบน AutoCAD จริง
- ทำทีละ Milestone และสรุปสั้นๆ ว่าอะไรทดสอบแล้ว อะไรยังรอทดสอบบนเครื่องผู้ใช้

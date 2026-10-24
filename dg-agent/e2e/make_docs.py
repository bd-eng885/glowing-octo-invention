# Generates SYNTHETIC SDS test documents (text PDF, scanned PDF, PNG). Not real product SDSs.
# Generates synthetic SDS documents for extraction testing (not real product SDSs).
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont
lines = ["SAFETY DATA SHEET", "SECTION 1: Identification", "Product name: Probe Degreaser 40",
 "Supplier: Example Chemicals Ltd", "Revision date: 2026-03-01", "SECTION 2: Hazards identification",
 "H225 Highly flammable liquid and vapour", "H301 Toxic if swallowed", "SECTION 3: Composition",
 "Methanol CAS 67-56-1 40-60%", "Toluene CAS 108-88-3 20-30%",
 "SECTION 14: Transport information", "UN number: UN1992",
 "UN proper shipping name: FLAMMABLE LIQUID, TOXIC, N.O.S. (methanol, toluene)",
 "Transport hazard class(es): 3 (6.1)", "Packing group: II", "Marine pollutant: No",
 "SECTION 15: Regulatory information"]
c = canvas.Canvas("sds_text.pdf", pagesize=A4); y = 800
for l in lines: c.drawString(50, y, l); y -= 20
c.save()
img = Image.new("RGB", (1700, 1000), "white"); d = ImageDraw.Draw(img)
f = ImageFont.truetype("DejaVuSans.ttf", 34); y = 30
for l in lines: d.text((40, y), l, fill="black", font=f); y += 52
img.save("scan.png"); img.save("sds_scanned.pdf", "PDF", resolution=150)
print("ok")

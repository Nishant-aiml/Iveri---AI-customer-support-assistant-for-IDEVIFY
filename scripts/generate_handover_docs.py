"""
Script to generate the two enterprise handover Word (.docx) documents:
1. Iveri_Enterprise_Installation_Setup_Operations_Manual.docx
2. Iveri_System_Architecture_and_Specifications_Blueprint.docx
"""

import os
import sys
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# --- Color Palette ---
COLOR_NAVY = RGBColor(15, 23, 42)       # #0F172A
COLOR_INDIGO = RGBColor(37, 99, 235)    # #2563EB
COLOR_SLATE_DARK = RGBColor(51, 65, 85) # #334155
COLOR_MUTED = RGBColor(100, 116, 139)   # #64748B
COLOR_EMERALD = RGBColor(16, 185, 129)  # #10B981
COLOR_AMBER = RGBColor(217, 119, 6)     # #D97706
COLOR_RED = RGBColor(225, 29, 72)       # #E11D48

HEX_NAVY = "0F172A"
HEX_HEADER_BG = "1E293B"
HEX_ROW_ALT = "F8FAFC"
HEX_BORDER = "CBD5E1"
HEX_CALLOUT_BG = "F1F5F9"
HEX_CALLOUT_BORDER = "2563EB"
HEX_WARN_BG = "FEF3C7"
HEX_WARN_BORDER = "D97706"
HEX_SUCCESS_BG = "ECFDF5"
HEX_SUCCESS_BORDER = "10B981"
HEX_CODE_BG = "F1F5F9"

def set_cell_background(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)

def set_cell_margins(cell, top=140, bottom=140, left=180, right=180):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def set_cell_border_left_only(cell, hex_color=HEX_CALLOUT_BORDER, sz="36"):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    
    left = OxmlElement('w:left')
    left.set(qn('w:val'), 'single')
    left.set(qn('w:sz'), sz)
    left.set(qn('w:space'), '0')
    left.set(qn('w:color'), hex_color)
    tcBorders.append(left)
    
    for b_name in ['top', 'right', 'bottom']:
        b = OxmlElement(f'w:{b_name}')
        b.set(qn('w:val'), 'none')
        tcBorders.append(b)
    tcPr.append(tcBorders)

def set_table_borders(table, hex_color=HEX_BORDER):
    tblPr = table._tbl.tblPr
    tblBorders = OxmlElement('w:tblBorders')
    for b_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        b = OxmlElement(f'w:{b_name}')
        b.set(qn('w:val'), 'single')
        b.set(qn('w:sz'), '4')
        b.set(qn('w:space'), '0')
        b.set(qn('w:color'), hex_color)
        tblBorders.append(b)
    tblPr.append(tblBorders)

def init_styled_doc():
    doc = docx.Document()
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
        # Header & Footer
        header = section.header
        hp = header.paragraphs[0]
        hp.text = "IVERI AI CUSTOMER SUPPORT PLATFORM  •  ENTERPRISE CLIENT HANDOVER"
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if hp.runs:
            hp.runs[0].font.name = "Calibri"
            hp.runs[0].font.size = Pt(8.5)
            hp.runs[0].font.color.rgb = COLOR_MUTED
            
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.text = "CONFIDENTIAL & PROPRIETARY  •  SYSTEM RELEASE 2.4.0 (GA)"
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if fp.runs:
            fp.runs[0].font.name = "Calibri"
            fp.runs[0].font.size = Pt(8.5)
            fp.runs[0].font.color.rgb = COLOR_MUTED
            
    return doc

def add_title_block(doc, title, subtitle, meta_items):
    # Top spacing
    p_pre = doc.add_paragraph()
    p_pre.paragraph_format.space_before = Pt(0)
    p_pre.paragraph_format.space_after = Pt(4)
    
    p_tag = doc.add_paragraph()
    p_tag.paragraph_format.space_before = Pt(0)
    p_tag.paragraph_format.space_after = Pt(6)
    r_tag = p_tag.add_run("OFFICIAL CLIENT HANDOVER DOSSIER")
    r_tag.font.name = "Calibri"
    r_tag.font.size = Pt(9.5)
    r_tag.font.bold = True
    r_tag.font.color.rgb = COLOR_INDIGO
    
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(6)
    r_title = p_title.add_run(title)
    r_title.font.name = "Calibri"
    r_title.font.size = Pt(24)
    r_title.font.bold = True
    r_title.font.color.rgb = COLOR_NAVY
    
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(16)
    r_sub = p_sub.add_run(subtitle)
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(13)
    r_sub.font.color.rgb = COLOR_SLATE_DARK
    
    # Metadata Table
    table = doc.add_table(rows=len(meta_items), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, HEX_BORDER)
    
    for idx, (label, val) in enumerate(meta_items):
        cell_label = table.cell(idx, 0)
        cell_val = table.cell(idx, 1)
        
        cell_label.width = Inches(2.2)
        cell_val.width = Inches(4.3)
        
        set_cell_background(cell_label, HEX_ROW_ALT)
        set_cell_background(cell_val, "FFFFFF")
        set_cell_margins(cell_label, 80, 80, 120, 120)
        set_cell_margins(cell_val, 80, 80, 120, 120)
        
        p_l = cell_label.paragraphs[0]
        p_l.paragraph_format.space_before = Pt(0)
        p_l.paragraph_format.space_after = Pt(0)
        r_l = p_l.add_run(label)
        r_l.font.name = "Calibri"
        r_l.font.size = Pt(9.5)
        r_l.font.bold = True
        r_l.font.color.rgb = COLOR_NAVY
        
        p_v = cell_val.paragraphs[0]
        p_v.paragraph_format.space_before = Pt(0)
        p_v.paragraph_format.space_after = Pt(0)
        r_v = p_v.add_run(val)
        r_v.font.name = "Calibri"
        r_v.font.size = Pt(9.5)
        r_v.font.color.rgb = COLOR_SLATE_DARK
        
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(14)
    p_space.paragraph_format.space_after = Pt(0)

def add_heading_1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(16)
    r.font.bold = True
    r.font.color.rgb = COLOR_NAVY
    return p

def add_heading_2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(13)
    r.font.bold = True
    r.font.color.rgb = COLOR_INDIGO
    return p

def add_heading_3(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(11)
    r.font.bold = True
    r.font.color.rgb = COLOR_SLATE_DARK
    return p

def add_p(doc, text, bold_prefix=None, italic=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_bp = p.add_run(bold_prefix)
        r_bp.font.name = "Calibri"
        r_bp.font.size = Pt(10)
        r_bp.font.bold = True
        r_bp.font.color.rgb = COLOR_NAVY
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(10)
    r.font.italic = italic
    r.font.color.rgb = COLOR_SLATE_DARK
    return p

def add_bullet(doc, text, bold_prefix=None):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_bp = p.add_run(bold_prefix)
        r_bp.font.name = "Calibri"
        r_bp.font.size = Pt(10)
        r_bp.font.bold = True
        r_bp.font.color.rgb = COLOR_NAVY
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(10)
    r.font.color.rgb = COLOR_SLATE_DARK
    return p

def add_callout(doc, text, title=None, alert_type="NOTE"):
    bg_color = HEX_CALLOUT_BG
    border_color = HEX_CALLOUT_BORDER
    title_color = COLOR_INDIGO
    
    if alert_type == "WARNING":
        bg_color = HEX_WARN_BG
        border_color = HEX_WARN_BORDER
        title_color = COLOR_AMBER
    elif alert_type == "SUCCESS":
        bg_color = HEX_SUCCESS_BG
        border_color = HEX_SUCCESS_BORDER
        title_color = COLOR_EMERALD
        
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    cell.width = Inches(6.5)
    
    set_cell_background(cell, bg_color)
    set_cell_border_left_only(cell, border_color, "36")
    set_cell_margins(cell, 120, 120, 180, 180)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.15
    
    if title:
        r_title = p.add_run(f"[{alert_type}] {title}\n")
        r_title.font.name = "Calibri"
        r_title.font.size = Pt(10)
        r_title.font.bold = True
        r_title.font.color.rgb = title_color
        
    r_text = p.add_run(text)
    r_text.font.name = "Calibri"
    r_text.font.size = Pt(9.5)
    r_text.font.color.rgb = COLOR_SLATE_DARK
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def add_code_block(doc, code_str):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    cell.width = Inches(6.5)
    
    set_cell_background(cell, HEX_CODE_BG)
    set_table_borders(table, HEX_BORDER)
    set_cell_margins(cell, 100, 100, 140, 140)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.05
    
    r = p.add_run(code_str.strip())
    r.font.name = "Consolas"
    r.font.size = Pt(8.5)
    r.font.color.rgb = COLOR_NAVY
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def add_table_data(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, HEX_BORDER)
    
    # Headers
    for c_idx, h_text in enumerate(headers):
        cell = table.cell(0, c_idx)
        if col_widths and c_idx < len(col_widths):
            cell.width = Inches(col_widths[c_idx])
        set_cell_background(cell, HEX_HEADER_BG)
        set_cell_margins(cell, 100, 100, 120, 120)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(h_text)
        r.font.name = "Calibri"
        r.font.size = Pt(9.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        
    # Rows
    for r_idx, row_data in enumerate(rows):
        bg = HEX_ROW_ALT if (r_idx % 2 == 1) else "FFFFFF"
        for c_idx, val in enumerate(row_data):
            cell = table.cell(r_idx + 1, c_idx)
            if col_widths and c_idx < len(col_widths):
                cell.width = Inches(col_widths[c_idx])
            set_cell_background(cell, bg)
            set_cell_margins(cell, 80, 80, 120, 120)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(str(val))
            r.font.name = "Calibri"
            r.font.size = Pt(9.0)
            r.font.color.rgb = COLOR_SLATE_DARK
            
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

print("Formatting helpers loaded successfully.")

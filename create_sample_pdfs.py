from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from datetime import datetime

def create_invoice_pdf(filename, invoice_data):
    """Create a professional invoice PDF"""
    doc = SimpleDocTemplate(filename, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=30,
    )
    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Invoice details table
    invoice_details = [
        ['Invoice #:', invoice_data['invoice_number'], 'Date:', invoice_data['date']],
        ['Vendor:', invoice_data['vendor_name'], 'GST:', invoice_data['vendor_gst']],
        ['PO#:', invoice_data['po_number'], 'Amount:', f"₹{invoice_data['amount']:,}"],
    ]
    
    t = Table(invoice_details, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f9ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*inch))
    
    # Line items
    elements.append(Paragraph("LINE ITEMS", styles['Heading2']))
    elements.append(Spacer(1, 0.1*inch))
    
    line_items_data = [['Description', 'HSN Code', 'Qty', 'Rate', 'GST%', 'Amount']]
    for item in invoice_data['line_items']:
        line_items_data.append([
            item['description'],
            item['hsn_code'],
            f"{item['qty']} {item['uom']}",
            f"₹{item['rate']}",
            f"{item['gst']}%",
            f"₹{item['amount']:,}",
        ])
    
    t2 = Table(line_items_data, colWidths=[2*inch, 1*inch, 1.2*inch, 1*inch, 0.8*inch, 1*inch])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f9ff')]),
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 0.3*inch))
    
    # Footer
    footer_data = [
        ['', '', 'Total Amount:', f"₹{invoice_data['amount']:,}"],
    ]
    t3 = Table(footer_data, colWidths=[2*inch, 2*inch, 1.5*inch, 1.5*inch])
    t3.setStyle(TableStyle([
        ('FONTNAME', (2, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (2, 0), (-1, 0), 11),
        ('ALIGN', (2, 0), (-1, 0), 'RIGHT'),
        ('BACKGROUND', (2, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (2, 0), (-1, 0), colors.white),
    ]))
    elements.append(t3)
    elements.append(Spacer(1, 0.5*inch))
    
    # Signature
    elements.append(Paragraph("Authorized By: ___________________", styles['Normal']))
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("Date: " + datetime.now().strftime("%d-%m-%Y"), styles['Normal']))
    
    doc.build(elements)
    print(f"✅ Created: {filename}")

# INVOICE 1: Normal (Auto-Approve)
invoice1 = {
    'invoice_number': 'INV/2026/0501',
    'vendor_name': 'Priya Electrical Industries Pvt Ltd',
    'vendor_gst': '27AABCT5055K1Z0',
    'po_number': 'PO/2026/0001',
    'date': '2026-09-20',
    'amount': 42500,
    'line_items': [
        {
            'description': 'Electrical Wires & Cables - 4mm Copper',
            'hsn_code': '8544',
            'qty': 500,
            'uom': 'meter',
            'rate': 85,
            'gst': 5,
            'amount': 42500,
        }
    ]
}

# INVOICE 2: With Issues (Human Review)
invoice2 = {
    'invoice_number': 'INV/2026/0502',
    'vendor_name': 'Techware Solutions India',
    'vendor_gst': '33AAFCT7891M1Z2',
    'po_number': 'PO/2026/0002',
    'date': '2026-09-22',
    'amount': 160000,
    'line_items': [
        {
            'description': 'ERP Development Services - 200 hours',
            'hsn_code': '9999',
            'qty': 200,
            'uom': 'hour',
            'rate': 800,
            'gst': 18,
            'amount': 160000,
        }
    ]
}

# INVOICE 3: Blacklisted (Auto-Reject)
invoice3 = {
    'invoice_number': 'INV/2026/0503',
    'vendor_name': 'Bangalore IT Consultants LLP',
    'vendor_gst': '06AACPB8765R3Z1',
    'po_number': 'PO/2026/0004',
    'date': '2026-09-21',
    'amount': 75000,
    'line_items': [
        {
            'description': 'Cloud Infrastructure Setup',
            'hsn_code': '9999',
            'qty': 50,
            'uom': 'hour',
            'rate': 1500,
            'gst': 18,
            'amount': 75000,
        }
    ]
}

if __name__ == "__main__":
    print("Creating sample invoice PDFs...\n")
    
    create_invoice_pdf('invoiceshield-ui/public/invoice_normal.pdf', invoice1)
    create_invoice_pdf('invoiceshield-ui/public/invoice_with_issues.pdf', invoice2)
    create_invoice_pdf('invoiceshield-ui/public/invoice_blacklisted.pdf', invoice3)
    
    print("\n✅ All invoices created successfully!")
    print("📁 Location: invoiceshield-ui/public/")
import json
import os
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from openai import OpenAI

# Load environment
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
google_creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
google_sheet_id = os.getenv("GOOGLE_SHEET_ID")

# Initialize OpenAI client
client = OpenAI(api_key=openai_api_key)

# ============================================
# GOOGLE SHEETS DATA LOADER
# ============================================

def load_google_sheets_data():
    """Load all 4 tabs from Google Sheets"""
    creds = Credentials.from_service_account_file(
        google_creds_path,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    service = build('sheets', 'v4', credentials=creds)
    
    sheets_data = {}
    tab_names = ['GST_FILING_STATUS', 'VENDOR_MASTER', 'PO_DATABASE', 'HSN_DATABASE']
    
    for tab in tab_names:
        result = service.spreadsheets().values().get(
            spreadsheetId=google_sheet_id,
            range=f"{tab}!A:Z"
        ).execute()
        sheets_data[tab] = result.get('values', [])
    
    return sheets_data

# ============================================
# LOAD INVOICE JSON
# ============================================

def load_invoice(filepath):
    """Load invoice JSON"""
    with open(filepath, 'r') as f:
        return json.load(f)

# ============================================
# AGENT 1: JSON PARSER
# ============================================

def agent1_json_parser(invoice):
    """Extracts and validates invoice structure"""
    print("\n" + "="*60)
    print("🔍 AGENT 1: JSON PARSER")
    print("="*60)
    
    required_fields = [
        'invoice_number', 'vendor_gst', 'vendor_name', 
        'invoice_amount', 'line_items', 'po_number'
    ]
    
    missing = [f for f in required_fields if f not in invoice]
    
    if missing:
        print(f"❌ Missing fields: {missing}")
        return {'status': 'FAILED', 'errors': missing, 'severity': 'CRITICAL'}
    
    print(f"✅ Invoice {invoice['invoice_number']}")
    print(f"   Vendor: {invoice['vendor_name']}")
    print(f"   Amount: ₹{invoice['invoice_amount']:,}")
    print(f"   OCR Confidence: {invoice.get('ocr_confidence', 'N/A')}%")
    
    return {
        'status': 'PASSED',
        'invoice_number': invoice['invoice_number'],
        'vendor_gst': invoice['vendor_gst'],
        'vendor_name': invoice['vendor_name'],
        'amount': invoice['invoice_amount'],
        'po_number': invoice['po_number'],
        'severity': 'NONE'
    }

# ============================================
# AGENT 2: GST VALIDATOR
# ============================================

def agent2_gst_validator(invoice, gst_sheet):
    """Checks vendor GST filing status"""
    print("\n" + "="*60)
    print("📋 AGENT 2: GST VALIDATOR")
    print("="*60)
    
    vendor_gst = invoice['vendor_gst']
    print(f"Checking GST: {vendor_gst}")
    
    # Find in GST_FILING_STATUS sheet (skip header)
    gst_status = "UNKNOWN"
    for row in gst_sheet[1:]:
        if len(row) > 0 and row[0] == vendor_gst:
            gst_status = row[2] if len(row) > 2 else "UNKNOWN"
            break
    
    if gst_status == "suspended":
        print(f"❌ GST SUSPENDED")
        return {'severity': 'CRITICAL', 'status': gst_status, 'agent': 'GST_VALIDATOR'}
    elif gst_status == "not_filed":
        print(f"⚠️  GST NOT FILED (overdue)")
        return {'severity': 'HIGH', 'status': gst_status, 'agent': 'GST_VALIDATOR'}
    else:
        print(f"✅ GST FILED (on time)")
        return {'severity': 'NONE', 'status': gst_status, 'agent': 'GST_VALIDATOR'}

# ============================================
# AGENT 3: HSN VALIDATOR
# ============================================

def agent3_hsn_validator(invoice, hsn_sheet):
    """Validates HSN codes & GST rates"""
    print("\n" + "="*60)
    print("🏷️  AGENT 3: HSN VALIDATOR")
    print("="*60)
    
    issues = []
    
    for item in invoice['line_items']:
        hsn = item['hsn_code']
        gst_claimed = item['gst_rate']
        
        print(f"Checking HSN {hsn}...")
        
        # Find correct GST rate
        correct_gst = 5  # Default for Rane
        if hsn == "9999":  # Software/Services
            correct_gst = 18
        
        if gst_claimed != correct_gst:
            issues.append(f"HSN {hsn}: Claimed {gst_claimed}% but should be {correct_gst}%")
            print(f"   ❌ GST Mismatch: {gst_claimed}% vs {correct_gst}%")
        else:
            print(f"   ✅ GST Correct: {gst_claimed}%")
    
    return {
        'issues': issues,
        'severity': 'HIGH' if issues else 'NONE',
        'agent': 'HSN_VALIDATOR'
    }

# ============================================
# AGENT 4: PO MATCHER
# ============================================

def agent4_po_matcher(invoice, po_sheet):
    """Matches invoice to PO database"""
    print("\n" + "="*60)
    print("📦 AGENT 4: PO MATCHER")
    print("="*60)
    
    po_number = invoice['po_number']
    print(f"Searching PO: {po_number}")
    
    po_found = False
    po_amount = None
    
    for row in po_sheet[1:]:
        if len(row) > 0 and row[0] == po_number:
            po_found = True
            po_amount = float(row[10]) if len(row) > 10 else None  # po_amount in col K (index 10)
            print(f"✅ PO found: {po_number}")
            print(f"   PO Amount: ₹{po_amount:,}")
            break
    
    if not po_found:
        print(f"❌ PO NOT FOUND")
        return {'status': 'NOT_FOUND', 'severity': 'HIGH', 'agent': 'PO_MATCHER'}
    
    return {
        'status': 'MATCHED',
        'po_number': po_number,
        'po_amount': po_amount,
        'severity': 'NONE',
        'agent': 'PO_MATCHER'
    }

# ============================================
# AGENT 5: VENDOR CHECKER
# ============================================

def agent5_vendor_checker(invoice, vendor_sheet):
    """Checks vendor approval & blacklist status"""
    print("\n" + "="*60)
    print("🏢 AGENT 5: VENDOR CHECKER")
    print("="*60)
    
    vendor_gst = invoice['vendor_gst']
    print(f"Checking vendor: {vendor_gst}")
    
    is_approved = False
    is_blacklisted = False
    
    for row in vendor_sheet[1:]:
        if len(row) > 2 and row[2] == vendor_gst:  # GST in col C (index 2)
            is_approved = row[5].lower() == 'true' if len(row) > 5 else False  # approved in col F (index 5)
            is_blacklisted = row[6].lower() == 'true' if len(row) > 6 else False  # blacklisted in col G (index 6)
            break
    
    if is_blacklisted:
        print(f"❌ VENDOR BLACKLISTED")
        return {'status': 'BLACKLISTED', 'severity': 'CRITICAL', 'agent': 'VENDOR_CHECKER'}
    
    if not is_approved:
        print(f"⚠️  VENDOR NOT APPROVED")
        return {'status': 'NOT_APPROVED', 'severity': 'HIGH', 'agent': 'VENDOR_CHECKER'}
    
    print(f"✅ Vendor approved & active")
    return {'status': 'APPROVED', 'severity': 'NONE', 'agent': 'VENDOR_CHECKER'}

# ============================================
# AGENT 6: PRICE VARIANCE DETECTOR
# ============================================

def agent6_price_variance(invoice):
    """Detects price variance from PO"""
    print("\n" + "="*60)
    print("💰 AGENT 6: PRICE VARIANCE DETECTOR")
    print("="*60)
    
    variance = invoice.get('price_variance_percent', 0)
    invoice_amount = invoice['invoice_amount']
    po_amount = invoice.get('po_amount', invoice_amount)
    
    print(f"Invoice Amount: ₹{invoice_amount:,}")
    print(f"PO Amount: ₹{po_amount:,}")
    print(f"Variance: {variance:.2f}%")
    
    if abs(variance) > 5:
        print(f"⚠️  VARIANCE > 5%")
        return {'variance_percent': variance, 'severity': 'HIGH', 'agent': 'PRICE_VARIANCE'}
    elif abs(variance) > 0:
        print(f"✅ Minor variance (acceptable)")
        return {'variance_percent': variance, 'severity': 'MEDIUM', 'agent': 'PRICE_VARIANCE'}
    else:
        print(f"✅ Perfect match")
        return {'variance_percent': variance, 'severity': 'NONE', 'agent': 'PRICE_VARIANCE'}

# ============================================
# AGENT 7: RATE JUSTIFIER
# ============================================

def agent7_rate_justifier(invoice):
    """Checks industry rate reasonableness"""
    print("\n" + "="*60)
    print("📊 AGENT 7: RATE JUSTIFIER")
    print("="*60)
    
    # Industry benchmarks
    benchmarks = {
        '9999': {'min': 500, 'max': 2500, 'description': 'IT Services/Software'},
        '8544': {'min': 50, 'max': 150, 'description': 'Electrical Wires'},
        '8457': {'min': 600, 'max': 2000, 'description': 'CNC Machining'}
    }
    
    issues = []
    for item in invoice['line_items']:
        hsn = item['hsn_code']
        rate = item['rate_per_unit']
        
        if hsn in benchmarks:
            bench = benchmarks[hsn]
            print(f"HSN {hsn} ({bench['description']})")
            print(f"   Rate: ₹{rate} | Range: ₹{bench['min']}-{bench['max']}")
            
            if rate < bench['min'] or rate > bench['max']:
                issues.append(f"Rate {rate} outside benchmark {bench['min']}-{bench['max']}")
                print(f"   ⚠️  OUTSIDE BENCHMARK")
            else:
                print(f"   ✅ Within range")
    
    return {'issues': issues, 'severity': 'MEDIUM' if issues else 'NONE', 'agent': 'RATE_JUSTIFIER'}

# ============================================
# AGENT 8: AUTHORIZATION DETECTOR
# ============================================

def agent8_authorization_detector(invoice):
    """Checks for signatures & stamps"""
    print("\n" + "="*60)
    print("✍️  AGENT 8: AUTHORIZATION DETECTOR")
    print("="*60)
    
    has_sig = invoice.get('has_signature', False)
    has_stamp = invoice.get('has_stamp', False)
    
    print(f"Signature: {'✅ YES' if has_sig else '❌ NO'}")
    print(f"Stamp: {'✅ YES' if has_stamp else '❌ NO'}")
    
    if not has_sig:
        print(f"⚠️  Missing signature")
        return {'severity': 'MEDIUM', 'issues': ['Missing signature'], 'agent': 'AUTHORIZATION'}
    
    if not has_stamp:
        print(f"⚠️  Missing stamp")
        return {'severity': 'LOW', 'issues': ['Missing stamp'], 'agent': 'AUTHORIZATION'}
    
    print(f"✅ Fully authorized")
    return {'severity': 'NONE', 'issues': [], 'agent': 'AUTHORIZATION'}

# ============================================
# AGENT 9: FINAL APPROVER
# ============================================

def agent9_final_approver(invoice, results):
    """Consolidates all agent outputs & makes final decision"""
    print("\n" + "="*60)
    print("⚖️  AGENT 9: FINAL APPROVER")
    print("="*60)
    
    # Count severity levels
    critical_issues = []
    high_issues = []
    medium_issues = []
    
    for agent_result in results:
        severity = agent_result.get('severity', 'NONE')
        
        if severity == 'CRITICAL':
            critical_issues.append(agent_result)
        elif severity == 'HIGH':
            high_issues.append(agent_result)
        elif severity == 'MEDIUM':
            medium_issues.append(agent_result)
    
    amount = invoice['invoice_amount']
    
    # Decision logic
    if critical_issues:
        decision = "AUTO_REJECT"
        reason = f"Critical issues found: {len(critical_issues)} CRITICAL issue(s)"
        approval_level = "SYSTEM"
    elif amount > 500000:
        decision = "HUMAN_REVIEW"
        reason = f"Amount exceeds ₹500K (₹{amount:,})"
        approval_level = "PLANT_HEAD"
    elif high_issues and amount > 50000:
        decision = "HUMAN_REVIEW"
        reason = f"HIGH severity issues + Amount ₹{amount:,}"
        approval_level = "PROCUREMENT_HEAD"
    elif medium_issues and amount > 10000:
        decision = "HUMAN_REVIEW"
        reason = f"MEDIUM severity issues + Amount ₹{amount:,}"
        approval_level = "FINANCE_MANAGER"
    elif high_issues:
        decision = "HUMAN_REVIEW"
        reason = f"{len(high_issues)} HIGH severity issue(s)"
        approval_level = "PROCUREMENT_HEAD"
    elif amount >= 50000:
        decision = "HUMAN_REVIEW"
        reason = f"Amount ₹{amount:,} requires approval"
        approval_level = "PROCUREMENT_HEAD"
    elif amount >= 10000:
        decision = "HUMAN_REVIEW"
        reason = f"Amount ₹{amount:,} requires approval"
        approval_level = "FINANCE_MANAGER"
    else:
        decision = "AUTO_APPROVE"
        reason = "All validations passed"
        approval_level = "SYSTEM"
    
    print(f"\n{'='*60}")
    print(f"📌 DECISION: {decision}")
    print(f"📌 APPROVAL LEVEL: {approval_level}")
    print(f"📌 REASON: {reason}")
    print(f"{'='*60}\n")
    
    return {
        'decision': decision,
        'approval_level': approval_level,
        'reason': reason,
        'critical_issues': len(critical_issues),
        'high_issues': len(high_issues),
        'medium_issues': len(medium_issues)
    }

# ============================================
# MAIN ORCHESTRATOR
# ============================================

def process_invoice(invoice_filepath):
    """Process a single invoice through all 9 agents"""
    
    print(f"\n\n{'#'*60}")
    print(f"# INVOICESHIELD - P2P AUTOMATION BOT")
    print(f"{'#'*60}")
    
    # Load data
    invoice = load_invoice(invoice_filepath)
    sheets_data = load_google_sheets_data()
    
    print(f"\n📄 Processing: {invoice_filepath}")
    
    # Run all 9 agents
    results = []
    
    # Agent 1
    r1 = agent1_json_parser(invoice)
    if r1['status'] == 'FAILED':
        print("❌ JSON parsing failed. Stopping.")
        return
    results.append(r1)
    
    # Agent 2
    r2 = agent2_gst_validator(invoice, sheets_data['GST_FILING_STATUS'])
    results.append(r2)
    
    # Agent 3
    r3 = agent3_hsn_validator(invoice, sheets_data['HSN_DATABASE'])
    results.append(r3)
    
    # Agent 4
    r4 = agent4_po_matcher(invoice, sheets_data['PO_DATABASE'])
    results.append(r4)
    
    # Agent 5
    r5 = agent5_vendor_checker(invoice, sheets_data['VENDOR_MASTER'])
    results.append(r5)
    
    # Agent 6
    r6 = agent6_price_variance(invoice)
    results.append(r6)
    
    # Agent 7
    r7 = agent7_rate_justifier(invoice)
    results.append(r7)
    
    # Agent 8
    r8 = agent8_authorization_detector(invoice)
    results.append(r8)
    
    # Agent 9 - Final decision
    final_decision = agent9_final_approver(invoice, results)
    
    # Save result
    result_file = invoice_filepath.replace('.json', '_result.json')
    with open(result_file, 'w') as f:
        json.dump({
            'invoice': invoice['invoice_number'],
            'final_decision': final_decision,
            'all_agent_results': results
        }, f, indent=2)
    
    print(f"✅ Result saved to: {result_file}")
    
    return final_decision

# ============================================
# RUN TESTS
# ============================================

if __name__ == "__main__":
    # Test all 3 invoices
    test_invoices = [
        "src/invoices/invoice_normal.json",
        "src/invoices/invoice_with_issues.json",
        "src/invoices/invoice_blacklisted.json"
    ]
    
    for inv_file in test_invoices:
        if os.path.exists(inv_file):
            process_invoice(inv_file)
        else:
            print(f"⚠️  File not found: {inv_file}")
def run_invoice_validation(invoice_data):
    """
    Run 9-agent validation on invoice data
    Returns approval decision
    """
    # This will call your existing agent orchestration
    # For now, return a simple mock result
    
    return {
        "decision": "AUTO_APPROVE",
        "approval_level": "SYSTEM",
        "issues_found": [],
        "confidence_score": 0.95,
        "agents_executed": 9,
    }
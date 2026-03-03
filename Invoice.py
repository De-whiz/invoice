import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    ConversationHandler,
    CallbackQueryHandler  # This was missing!
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
import uuid
import tempfile

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
CLIENT_NAME, SERVICE, PRICE, QUANTITY, ADD_MORE, PAYMENT_DATE, PAYMENT_METHOD = range(7)

# Company branding
COMPANY_NAME = "Tachaelhub"
COLORS = {
    'white': colors.white,
    'deep_blue': colors.HexColor('#1a237e'),
    'gold': colors.HexColor('#ffd700')
}

class InvoiceData:
    def __init__(self):
        self.client_name = ""
        self.items = []
        self.invoice_number = ""
        self.payment_date = ""
        self.payment_method = ""
        
    def reset(self):
        self.client_name = ""
        self.items = []
        self.invoice_number = ""
        self.payment_date = ""
        self.payment_method = ""
        
    def add_item(self, service, price, quantity):
        self.items.append({
            'service': service,
            'price': float(price),
            'quantity': int(quantity)
        })
        
    def calculate_total(self):
        return sum(item['price'] * item['quantity'] for item in self.items)
    
    def generate_invoice_number(self):
        date_str = datetime.now().strftime("%Y%m")
        unique_id = str(uuid.uuid4())[:8].upper()
        self.invoice_number = f"INV-{date_str}-{unique_id}"
        return self.invoice_number

# Store user data (in production, use a database)
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user_id = update.effective_user.id
    user_data[user_id] = InvoiceData()
    
    welcome_message = (
        f"🏢 *Welcome to {COMPANY_NAME} Invoice Generator!*\n\n"
        "I'll help you create professional after-payment invoices.\n"
        "Let's start by entering the client information.\n\n"
        "Please enter the *client name*:"
    )
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')
    return CLIENT_NAME

async def client_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client name input"""
    user_id = update.effective_user.id
    if user_id not in user_data:
        user_data[user_id] = InvoiceData()
    
    user_data[user_id].client_name = update.message.text
    
    await update.message.reply_text(
        f"Client: *{update.message.text}*\n\n"
        "Now, tell me about the first item/service:\n"
        "Please enter the *service description*:",
        parse_mode='Markdown'
    )
    return SERVICE

async def service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle service description"""
    context.user_data['current_service'] = update.message.text
    
    await update.message.reply_text(
        f"Service: *{update.message.text}*\n\n"
        "Enter the *price* (in Naira):",
        parse_mode='Markdown'
    )
    return PRICE

async def price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price input"""
    try:
        price = float(update.message.text)
        context.user_data['current_price'] = price
        
        await update.message.reply_text(
            f"Price: *{price:,.2f} Naira*\n\n"
            "Enter the *quantity*:",
            parse_mode='Markdown'
        )
        return QUANTITY
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid price. Please enter a number (e.g., 5000):"
        )
        return PRICE

async def quantity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quantity input and add item"""
    try:
        quantity = int(update.message.text)
        user_id = update.effective_user.id
        
        # Add item to invoice
        service = context.user_data.get('current_service', '')
        price = context.user_data.get('current_price', 0)
        
        user_data[user_id].add_item(service, price, quantity)
        
        # Show item added confirmation
        item_total = price * quantity
        await update.message.reply_text(
            f"✅ *Item added successfully!*\n\n"
            f"Service: {service}\n"
            f"Quantity: {quantity}\n"
            f"Price: {price:,.2f} Naira\n"
            f"Item Total: {item_total:,.2f} Naira\n\n"
            f"Current total: {user_data[user_id].calculate_total():,.2f} Naira",
            parse_mode='Markdown'
        )
        
        # Ask if they want to add more
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, add another", callback_data="add_more"),
                InlineKeyboardButton("📄 No, generate invoice", callback_data="generate")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Do you want to add another item?",
            reply_markup=reply_markup
        )
        return ADD_MORE
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid quantity. Please enter a whole number (e.g., 2):"
        )
        return QUANTITY

async def add_more_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the add more / generate choice"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_more":
        await query.edit_message_text(
            "Great! Enter the next *service description*:",
            parse_mode='Markdown'
        )
        return SERVICE
    else:
        # Ask for payment date
        await query.edit_message_text(
            "Now, let's add payment details.\n\n"
            "Enter the *payment date* (YYYY-MM-DD) [or 'today' for today's date]:",
            parse_mode='Markdown'
        )
        return PAYMENT_DATE

async def payment_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment date input"""
    user_id = update.effective_user.id
    date_text = update.message.text.lower()
    
    if date_text == 'today':
        payment_date = datetime.now().strftime("%Y-%m-%d")
    else:
        payment_date = date_text
        
    user_data[user_id].payment_date = payment_date
    
    await update.message.reply_text(
        f"Payment date: *{payment_date}*\n\n"
        "Enter *payment method* (Bank Transfer/Cash/USSD/etc):",
        parse_mode='Markdown'
    )
    return PAYMENT_METHOD

async def payment_method_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment method and generate invoice"""
    user_id = update.effective_user.id
    user_data[user_id].payment_method = update.message.text
    
    # Generate invoice number
    user_data[user_id].generate_invoice_number()
    
    await update.message.reply_text(
        "⏳ *Generating your invoice...*",
        parse_mode='Markdown'
    )
    
    # Generate PDF
    try:
        pdf_path = await generate_invoice_pdf(user_data[user_id])
        
        # Send PDF
        with open(pdf_path, 'rb') as pdf_file:
            await update.message.reply_document(
                document=pdf_file,
                filename=f"Tachaelhub_Invoice_{user_data[user_id].invoice_number}.pdf",
                caption=f"✅ *Invoice generated successfully!*\nInvoice #: {user_data[user_id].invoice_number}",
                parse_mode='Markdown'
            )
        
        # Clean up temp file
        os.unlink(pdf_path)
        
        # Ask to start over
        keyboard = [[InlineKeyboardButton("🔄 Create New Invoice", callback_data="new_invoice")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "What would you like to do next?",
            reply_markup=reply_markup
        )
        
        # Clear user data
        del user_data[user_id]
        
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        await update.message.reply_text(
            "❌ Sorry, there was an error generating the invoice. Please try again."
        )
    
    return ConversationHandler.END

async def new_invoice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new invoice button"""
    query = update.callback_query
    await query.answer()
    
    # Start new invoice
    user_id = update.effective_user.id
    user_data[user_id] = InvoiceData()
    
    await query.edit_message_text(
        "🏢 Starting new invoice...\n\nPlease enter the *client name*:",
        parse_mode='Markdown'
    )
    return CLIENT_NAME

async def generate_invoice_pdf(invoice_data):
    """Generate PDF invoice"""
    # Create temp file
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    
    # Create PDF
    doc = SimpleDocTemplate(path, pagesize=A4)
    elements = []
    
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=COLORS['deep_blue'],
        alignment=TA_CENTER,
        spaceAfter=10
    )
    
    # Company header
    header_text = f"""
    <font color='#1a237e' size='28'><b>{COMPANY_NAME}</b></font>
    """
    elements.append(Paragraph(header_text, title_style))
    
    elements.append(Spacer(1, 0.2*inch))
    
    # Payment confirmation banner
    paid_text = """
    <para alignment='center'>
    <font color='#ffd700' size='16'><b>✓ PAYMENT RECEIPT / INVOICE ✓</b></font>
    </para>
    """
    elements.append(Paragraph(paid_text, styles['Normal']))
    
    elements.append(Spacer(1, 0.3*inch))
    
    # Invoice details
    details_data = [
        ['Invoice Number:', invoice_data.invoice_number, 'Payment Date:', invoice_data.payment_date],
        ['Client:', invoice_data.client_name, 'Payment Method:', invoice_data.payment_method],
        ['Status:', '✅ PAID', '', '']
    ]
    
    details_table = Table(details_data, colWidths=[80, 150, 80, 150])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), COLORS['deep_blue']),
        ('TEXTCOLOR', (2, 0), (2, -1), COLORS['deep_blue']),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(details_table)
    
    elements.append(Spacer(1, 0.3*inch))
    
    # Items table header
    items_header = Paragraph(
        "<font color='#1a237e' size='12'><b>ITEMS/SERVICES PURCHASED</b></font>",
        styles['Normal']
    )
    elements.append(items_header)
    elements.append(Spacer(1, 0.1*inch))
    
    # Items table
    table_data = [['Item', 'Description', 'Qty', 'Unit Price (Naira)', 'Total (Naira)']]
    
    for i, item in enumerate(invoice_data.items, 1):
        total = item['price'] * item['quantity']
        table_data.append([
            str(i),
            item['service'],
            str(item['quantity']),
            f"{item['price']:,.2f}",
            f"{total:,.2f}"
        ])
    
    items_table = Table(table_data, colWidths=[40, 250, 40, 90, 90])
    items_table.setStyle(TableStyle([
        # Header style
        ('BACKGROUND', (0, 0), (-1, 0), COLORS['deep_blue']),
        ('TEXTCOLOR', (0, 0), (-1, 0), COLORS['white']),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        
        # Table body style
        ('BACKGROUND', (0, 1), (-1, -1), COLORS['white']),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        
        # Grid lines
        ('GRID', (0, 0), (-1, -1), 1, COLORS['deep_blue']),
        ('LINEBELOW', (0, 0), (-1, 0), 2, COLORS['gold']),
    ]))
    elements.append(items_table)
    
    elements.append(Spacer(1, 0.3*inch))
    
    # Total
    total_amount = invoice_data.calculate_total()
    
    # Totals table
    totals_data = [
        ['Subtotal:', f"{total_amount:,.2f} Naira"],
        ['', ''],
        ['TOTAL AMOUNT PAID:', f"{total_amount:,.2f} Naira"],
    ]
    
    totals_table = Table(totals_data, colWidths=[400, 150])
    totals_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('FONTSIZE', (0, 2), (1, 2), 14),
        ('FONTNAME', (0, 2), (1, 2), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 2), (1, 2), COLORS['deep_blue']),
        ('BACKGROUND', (0, 2), (1, 2), COLORS['gold']),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(totals_table)
    
    elements.append(Spacer(1, 0.5*inch))
    
    # Footer
    footer_text = f"""
    <para alignment='center'>
    <font color='#1a237e' size='10'>
    <b>{COMPANY_NAME}</b> - Official Payment Receipt<br/>
    This document serves as proof of payment. Thank you for your business!<br/>
    For inquiries, please reference invoice: {invoice_data.invoice_number}
    </font>
    </para>
    """
    footer = Paragraph(footer_text, styles['Normal'])
    elements.append(footer)
    
    # Build PDF
    doc.build(elements)
    
    return path

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    await update.message.reply_text(
        "❌ Invoice generation cancelled. Use /start to begin again."
    )
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    help_text = (
        "🤖 *Tachaelhub Invoice Bot Commands:*\n\n"
        "/start - Start creating a new invoice\n"
        "/help - Show this help message\n"
        "/cancel - Cancel current operation\n\n"
        "*How it works:*\n"
        "1. Start with /start\n"
        "2. Enter client name\n"
        "3. Add item(s) with description, price, quantity\n"
        "4. Add payment date and method\n"
        "5. Receive PDF invoice"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    """Main function to run the bot"""
    # Replace with your bot token from BotFather
    TOKEN = "8675320434:AAHwgGm-meyMwaSWM52u9Atzrqt48BIhxJ8"  # <-- PUT YOUR TOKEN HERE
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_name_handler)],
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, service_handler)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price_handler)],
            QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_handler)],
            ADD_MORE: [CallbackQueryHandler(add_more_handler, pattern="^(add_more|generate)$")],
            PAYMENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_date_handler)],
            PAYMENT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_method_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CallbackQueryHandler(new_invoice_callback, pattern="^new_invoice$"))
    
    # Start the bot
    print("🤖 Bot is running... Press Ctrl+C to stop")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
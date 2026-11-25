"""Backend-owned assistant copy, merged with existing editable label dictionaries."""


def ai_labels():
    return {
        'ai_title': 'Jewellery assistant', 'ai_open': 'Ask our stylist',
        'ai_intro': 'Tell me your occasion, outfit and budget. You can also share a dress or face photo for style suggestions.',
        'ai_message': 'Your message', 'ai_send': 'Send', 'ai_close': 'Close assistant',
        'ai_photo': 'Optional outfit or face photo', 'ai_remove_photo': 'Remove photo',
        'ai_privacy': 'Your message and optional photo are sent to Google Gemini. Photos are processed temporarily and are not saved by this store. Provider data terms apply. Do not upload photos without permission.',
        'ai_consent': 'I agree to send this photo to Gemini for style suggestions.',
        'ai_busy': 'Preparing suggestions…', 'ai_unavailable': 'The assistant is unavailable. Please browse the catalog or try later.',
        'ai_limit': 'The assistant usage limit has been reached. Please browse the catalog and try again later.',
        'ai_invalid': 'Check your message, price, stock and photos, then try again.',
        'ai_failed': 'The assistant could not complete this request. Please try again later.',
        'ai_product_title': 'Create product with AI', 'ai_product_help': 'Upload photos of one product and enter its price. Review the suggested details before saving. Omitted stock means one piece.',
        'ai_photos': 'Product photos', 'ai_price': 'Price', 'ai_stock': 'Stock (defaults to 1)',
        'ai_notes': 'Confirmed facts / supplier notes', 'ai_generate': 'Prepare product',
        'ai_review': 'Review product', 'ai_unknowns': 'Check these facts before publishing',
        'ai_main': 'Cover photo', 'ai_gallery': 'Gallery order', 'ai_save': 'Approve and save',
        'ai_active': 'Publish on storefront', 'ai_saved': 'Product saved',
        'ai_expired': 'This draft expired. Prepare a new product draft.',
        'ai_grouping': 'These photos may show different products or variants. Upload one product at a time and clarify your notes.',
        'ai_new': 'Start another product', 'ai_catalog': 'Browse jewellery',
        'ai_move_up': 'Move photo earlier', 'ai_move_down': 'Move photo later',
    }

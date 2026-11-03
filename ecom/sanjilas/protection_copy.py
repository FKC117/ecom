def customer_copy():
    return {
        'shop_order_blocked':'We cannot accept this request right now. Please contact the store for help.',
        'shop_order_limited':'Too many attempts. Please wait 10 minutes before trying again.',
        'shop_duplicate_order':'An order for these items was already placed with this phone number recently. Please check your orders or contact the store before ordering again.',
        'shop_cart_limit':'Your bag exceeds the store’s item limit. Reduce the quantity or contact the store for a larger order.',
    }


def staff_copy():
    return {
        'review_title':'Order review', 'review_help':'Check the customer and order details before approval. These signals do not prove fraud. Rejecting cancels the order and restores stock; any real payment still needs refund handling.',
        'review_clear':'No review needed', 'review_pending':'Needs review', 'review_approved':'Approved', 'review_rejected':'Rejected',
        'review_open_phone':'Several open orders share this phone number.',
        'review_cancelled_phone':'This phone number has several recently cancelled orders.',
        'review_busy_ip':'Several recent orders share this IP. Shared connections can be legitimate.',
        'review_shared_browser':'This browser was used by several accounts recently.',
        'review_reason':'Review reason', 'review_approve':'Approve order', 'review_reject':'Reject and cancel order',
        'review_save':'Save decision', 'review_decision':'Decision', 'review_history':'Review history',
        'review_queue':'Needs review only', 'review_stale':'This review changed. Refresh before deciding again.',
    }

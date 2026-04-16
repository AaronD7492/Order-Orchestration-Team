let editingId = null;
let editingQty = 1;

const displayFreqLabels = {
    daily: 'Daily',
    weekly: 'Weekly',
    'biweekly': 'Biweekly',
    monthly: 'Monthly',
    '3months': 'Every 3 months',
    '6months': 'Every 6 months',
    yearly: 'Yearly'
};

async function fetchSubscriptions() {
    const grid = document.getElementById('subsGrid');
    try {
        const response = await fetch('/api/subscriptions', {
            method: 'GET',
            credentials: 'same-origin'
        });
        if (response.status === 401) throw new Error('401');
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.message || 'Service unavailable');
        }
        const data = await response.json();
        grid.innerHTML = '';
        if (data.length === 0) {
            grid.innerHTML = '<p class="no-subs">You have no active subscriptions.</p>';
            document.getElementById('subsCount').textContent = '0 active';
            return;
        }
        data.forEach(sub => {
            const cardHTML = `
                <div class="sub-card" id="sub-${sub.id}">
                    <div class="sub-card-header">
                        <div class="sub-product-name">${sub.product_name}</div>
                        <span class="sub-status">Active</span>
                    </div>
                    <div class="sub-details">
                        <div class="sub-detail">
                            <span class="sub-detail-label">Frequency</span>
                            <span class="sub-detail-value" id="freq-${sub.id}">${displayFreqLabels[sub.occurence] || sub.occurence}</span>
                        </div>
                        <div class="sub-detail">
                            <span class="sub-detail-label">Quantity</span>
                            <span class="sub-detail-value" id="qty-${sub.id}">${sub.quantity}</span>
                        </div>
                        <div class="sub-detail">
                            <span class="sub-detail-label">Next Order</span>
                            <span class="sub-detail-value">${formatDate(sub.next_order)}</span>
                        </div>
                    </div>
                    <div class="sub-actions">
                        <button class="sub-action-btn edit-freq" onclick="openEditFreq(${sub.id}, '${sub.occurence}')">Edit Frequency</button>
                        <button class="sub-action-btn edit-qty" onclick="openEditQty(${sub.id}, ${sub.quantity})">Edit Quantity</button>
                        <button class="sub-action-btn cancel" onclick="confirmCancel(${sub.id})">Cancel</button>
                    </div>
                </div>`;
            grid.insertAdjacentHTML('beforeend', cardHTML);
        });
        document.getElementById('subsCount').textContent = `${data.length} active`;
    } catch (err) {
        const msg = err.message && err.message.includes('401')
            ? 'Please log in to view your subscriptions.'
            : 'The subscription service is temporarily unavailable. Please try again later.';
        grid.innerHTML = `<p class="no-subs" style="color:#dc2626;">${msg}</p>`;
        document.getElementById('subsCount').textContent = '—';
        console.error('Fetch Error:', err);
    }
}

function openEditFreq(id, currentFreq) {
    editingId = id;
    document.getElementById('editFreqSelect').value = currentFreq;
    document.getElementById('editFreqModal').classList.add('open');
}
function closeEditFreq() { document.getElementById('editFreqModal').classList.remove('open'); }

async function saveFreq() {
    const newVal = document.getElementById('editFreqSelect').value;
    try {
        const response = await fetch('/api/subscriptions', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: editingId, occurence: newVal }),
            credentials: 'same-origin'
        });
        if (response.ok) {
            document.getElementById('freq-' + editingId).textContent = displayFreqLabels[newVal];
            closeEditFreq();
            fetchSubscriptions();
        }
    } catch (err) { console.error('Update error:', err); }
}

function openEditQty(id, currentQty) {
    editingId = id;
    editingQty = parseInt(currentQty);
    document.getElementById('editQtyDisplay').textContent = editingQty;
    document.getElementById('editQtyModal').classList.add('open');
}
function closeEditQty() { document.getElementById('editQtyModal').classList.remove('open'); }
function changeEditQty(delta) {
    editingQty = Math.max(1, editingQty + delta);
    document.getElementById('editQtyDisplay').textContent = editingQty;
}

async function saveQty() {
    try {
        const response = await fetch('/api/subscriptions', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: editingId, qty: editingQty }),
            credentials: 'same-origin'
        });
        if (response.ok) {
            document.getElementById('qty-' + editingId).textContent = editingQty;
            closeEditQty();
        }
    } catch (err) { console.error('Update error:', err); }
}

function confirmCancel(id) {
    editingId = id;
    document.getElementById('cancelModal').classList.add('open');
}
function closeCancelModal() { document.getElementById('cancelModal').classList.remove('open'); }

async function cancelSubscription() {
    try {
        const response = await fetch('/api/subscriptions', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subscription_id: editingId }),
            credentials: 'same-origin'
        });
        if (response.ok) {
            const card = document.getElementById('sub-' + editingId);
            card.style.transition = 'opacity 0.3s, transform 0.3s';
            card.style.opacity = '0';
            card.style.transform = 'scale(0.95)';
            setTimeout(() => { card.remove(); fetchSubscriptions(); }, 300);
            closeCancelModal();
        } else {
            alert('Error: Could not cancel subscription.');
        }
    } catch (err) { console.error('Delete Error:', err); }
}

function formatDate(dateString) {
    if (!dateString) return 'Pending';
    const options = { day: 'numeric', month: 'short', year: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-GB', options);
}

document.addEventListener('DOMContentLoaded', fetchSubscriptions);
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeEditFreq(); closeEditQty(); closeCancelModal(); }
});

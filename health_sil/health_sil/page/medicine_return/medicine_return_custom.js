(function() {
  function findWrapper() {
    let el = document.querySelector('.mr-wrapper');
    if (el) return el;
    // Check shadow roots of all elements
    const all = document.querySelectorAll('*');
    for (let i = 0; i < all.length; i++) {
      try {
        const sr = all[i].shadowRoot;
        if (sr) {
          const wrapper = sr.querySelector('.mr-wrapper');
          if (wrapper) return wrapper;
        }
      } catch (e) {}
    }
    return null;
  }

  // Wait until both frappe is loaded and wrapper element is in the DOM
  const checkReady = setInterval(() => {
    const wrapper = findWrapper();
    if (typeof frappe !== 'undefined' && wrapper) {
      clearInterval(checkReady);
      initMedicineReturn(wrapper);
    }
  }, 100);

  function initMedicineReturn(wrapper) {
    // Prevent Frappe's global keydown shortcuts from stealing input focus
    wrapper.addEventListener('keydown', function(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        e.stopPropagation();
      }
    });

    // --- State ---
    let _billDoc = null;
    let _medicines = [];
    let _walkinItems = [];
    const RETURN_DEDUCTION_PCT = 12;

    // --- DOM Selectors (scoped to our wrapper) ---
    const $ = (sel) => wrapper.querySelector(sel);
    const $$ = (sel) => wrapper.querySelectorAll(sel);

    // --- UI Elements ---
    const tabs = $$('.mr-tab');
    const modeBill = $('#mr-mode-bill');
    const modePatient = $('#mr-mode-patient');
    const modeWalkin = $('#mr-mode-walkin');

    const billIdInput = $('#mr-bill-id');
    const searchBtn = $('#mr-search-btn');
    const billInfoDiv = $('#mr-bill-info');
    const step2Div = $('#mr-step2');
    const tbody = $('#mr-medicine-tbody');
    const selectAllCb = $('#mr-select-all');
    const summaryDiv = $('#mr-summary');
    const actionBar = $('#mr-action-bar');
    const processBtn = $('#mr-process-btn');
    const printBtn = $('#mr-print-btn');
    const spinner = $('#mr-spinner');
    const resultBanner = $('#mr-result-banner');

    // --- Mode Tab Switching ---
    tabs.forEach(tab => {
      tab.addEventListener('click', function() {
        tabs.forEach(t => t.classList.remove('active'));
        this.classList.add('active');
        const mode = this.getAttribute('data-mode');
        
        modeBill.style.display = mode === 'bill' ? 'block' : 'none';
        modePatient.style.display = mode === 'patient' ? 'block' : 'none';
        modeWalkin.style.display = mode === 'walkin' ? 'block' : 'none';

        if (mode !== 'walkin') {
          if (_billDoc) {
            billInfoDiv.style.display = 'block';
            step2Div.style.display = 'block';
            actionBar.style.display = 'flex';
          }
        } else {
          billInfoDiv.style.display = 'none';
          step2Div.style.display = 'none';
          actionBar.style.display = 'none';
        }
      });
    });

    // --- Helpers ---
    const flt = (v) => parseFloat(v) || 0;
    const fmt = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    
    function showBanner(msg, type) {
      resultBanner.textContent = msg;
      resultBanner.className = "mr-result-banner " + (type === 'error' ? 'mr-error' : 'mr-success');
      resultBanner.style.display = 'block';
    }

    function showSpinner(show) {
      spinner.style.display = show ? 'flex' : 'none';
    }

    function fmtDate(d) {
      if (!d) return "—";
      try {
        var parts = d.split("-");
        if (parts.length === 3) return parts[2] + "-" + parts[1] + "-" + parts[0];
      } catch(e){}
      return d;
    }

    // --- Step 1: By Bill ID ---
    searchBtn.addEventListener('click', fetchBill);
    billIdInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') fetchBill(); });

    function fetchBill() {
      const billId = (billIdInput.value || "").trim();
      if (!billId) {
        frappe.msgprint ? frappe.msgprint("Please enter a Bill ID.") : alert("Please enter a Bill ID.");
        return;
      }

      resultBanner.style.display = 'none';
      showSpinner(true);
      billInfoDiv.style.display = 'none';
      step2Div.style.display = 'none';
      tbody.innerHTML = '';

      frappe.call({
        method: "frappe.client.get",
        args: { doctype: "Pharmacy Billing", name: billId },
        callback: function(r) {
          showSpinner(false);
          if (!r || !r.message) {
            showBanner("❌ Bill '" + billId + "' not found.", "error");
            return;
          }
          const doc = r.message;
          if (doc.docstatus !== 1) {
            showBanner("⚠️ This bill is not submitted. Only submitted bills can be returned.", "error");
            return;
          }

          _billDoc = doc;
          _medicines = doc.medicines || [];

          if (_medicines.length === 0) {
            showBanner("⚠️ This bill has no medicines.", "error");
            return;
          }

          renderBillInfo(doc);
          renderMedicineTable(_medicines);
          billInfoDiv.style.display = 'block';
          step2Div.style.display = 'block';
          actionBar.style.display = 'flex';
          recalcSummary();
        },
        error: function() {
          showSpinner(false);
          showBanner("❌ Error fetching bill.", "error");
        }
      });
    }

    function renderBillInfo(doc) {
      $('#mr-info-name').textContent = doc.name || "—";
      $('#mr-info-patient').textContent = doc.patient_name || "—";
      $('#mr-info-date').textContent = fmtDate((doc.date_and_time || "").split(" ")[0]);
      $('#mr-info-doctor').textContent = doc.healthcare_practitioner || "—";
      $('#mr-info-total').textContent = fmt(doc.rounded_total_amount || doc.total_amount);
    }

    function renderMedicineTable(medicines) {
      tbody.innerHTML = "";
      medicines.forEach((med, idx) => {
        const tr = document.createElement("tr");
        const billedQty = flt(med.qty);
        tr.innerHTML = `
          <td style="text-align:center;"><input type="checkbox" class="mr-row-checkbox" data-idx="${idx}" /></td>
          <td>${med.hsn || "—"}</td>
          <td style="font-weight:600;">${med.item_name || med.item_code || "—"}</td>
          <td>${med.batch || "—"}</td>
          <td>${fmtDate(med.expiry_date) || "—"}</td>
          <td style="text-align:center; font-weight:600;">${billedQty}</td>
          <td style="text-align:center;">
            <input type="number" class="mr-ret-qty-input" id="mr-retqty-${idx}" min="0" max="${billedQty}" value="${billedQty}" disabled data-idx="${idx}" data-max="${billedQty}" style="width: 70px;" />
          </td>
          <td style="text-align:right;">${fmt(med.mrp)}</td>
          <td style="text-align:right;">${(flt(med.discount_) || 0).toFixed(2)}%</td>
          <td style="text-align:right;">${med.gst_ || "0"}%</td>
          <td style="text-align:right; font-weight:600;">${fmt(med.amount)}</td>
        `;
        tbody.appendChild(tr);

        const cb = tr.querySelector(".mr-row-checkbox");
        cb.addEventListener('change', function() {
          const qtyInput = $(`#mr-retqty-${idx}`);
          if (this.checked) {
            tr.classList.add("mr-row-selected");
            qtyInput.disabled = false;
          } else {
            tr.classList.remove("mr-row-selected");
            qtyInput.disabled = true;
          }
          recalcSummary();
          syncSelectAll();
        });

        const qi = $(`#mr-retqty-${idx}`);
        qi.addEventListener('input', function() {
          const maxQ = flt(this.dataset.max);
          let val = flt(this.value);
          if (val < 0) this.value = 0;
          if (val > maxQ) this.value = maxQ;
          recalcSummary();
        });
      });
    }

    function syncSelectAll() {
      const cbs = $$(".mr-row-checkbox");
      const checked = Array.from(cbs).filter(c => c.checked).length;
      if (selectAllCb) {
        selectAllCb.indeterminate = checked > 0 && checked < cbs.length;
        selectAllCb.checked = checked === cbs.length;
      }
    }

    if (selectAllCb) {
      selectAllCb.addEventListener('change', function() {
        const state = this.checked;
        $$(".mr-row-checkbox").forEach(cb => {
          cb.checked = state;
          const tr = cb.closest("tr");
          const qi = $(`#mr-retqty-${cb.dataset.idx}`);
          if (state) {
            tr.classList.add("mr-row-selected");
            if (qi) qi.disabled = false;
          } else {
            tr.classList.remove("mr-row-selected");
            if (qi) qi.disabled = true;
          }
        });
        recalcSummary();
      });
    }

    function getSelectedItems() {
      const cbs = $$(".mr-row-checkbox");
      const result = [];
      cbs.forEach(cb => {
        if (!cb.checked) return;
        const idx = parseInt(cb.dataset.idx, 10);
        const med = _medicines[idx];
        if (!med) return;
        const retQtyInput = $(`#mr-retqty-${idx}`);
        const retQty = retQtyInput ? flt(retQtyInput.value) : flt(med.qty);
        if (retQty <= 0) return;

        const billedQty = flt(med.qty) || 1;
        const grossAmount = (flt(med.amount) / billedQty) * retQty;
        const deductionAmt = grossAmount * (RETURN_DEDUCTION_PCT / 100);
        const retAmount = grossAmount - deductionAmt;

        result.push({
          item_code: med.item_code,
          item_name: med.item_name,
          batch: med.batch,
          hsn: med.hsn,
          expiry_date: med.expiry_date,
          mrp: flt(med.mrp),
          discount_: flt(med.discount_),
          gst_: med.gst_,
          billedQty: billedQty,
          retQty: retQty,
          grossAmount: grossAmount,
          deductionAmt: deductionAmt,
          retAmount: retAmount
        });
      });
      return result;
    }

    function recalcSummary() {
      const selected = getSelectedItems();
      const totalGross = selected.reduce((s, m) => s + m.grossAmount, 0);
      const totalNet = selected.reduce((s, m) => s + m.retAmount, 0);

      $('#mr-ret-items').textContent = selected.length;
      $('#mr-ret-qty').textContent = selected.reduce((s, m) => s + m.retQty, 0);

      const retTotalEl = $('#mr-ret-total');
      if (retTotalEl) {
        retTotalEl.innerHTML = `
          <span style="font-size:13px; color:#8d99a6; text-decoration:line-through;">${fmt(totalGross)}</span>
          <span style="font-size:11px; color:#e53e3e; margin-left:6px;">-${RETURN_DEDUCTION_PCT}% policy</span><br>
          <span style="font-size:24px; font-weight:800; color:#e53e3e;">${fmt(totalNet)}</span>
        `;
      }

      summaryDiv.style.display = selected.length > 0 ? 'flex' : 'none';
      processBtn.disabled = selected.length === 0;
    }

    // --- Process Bill ID Returns ---
    processBtn.addEventListener('click', function() {
      const selected = getSelectedItems();
      if (selected.length === 0) return;

      const totalRefund = selected.reduce((s, m) => s + m.retAmount, 0);
      if (!confirm(`Return ${selected.length} item(s) - Refund: ${fmt(totalRefund)}?`)) return;

      resultBanner.style.display = 'none';
      showSpinner(true);
      processBtn.disabled = true;

      const payload = selected.map(m => ({
        item_code: m.item_code,
        batch: m.batch,
        qty: m.retQty
      }));

      frappe.call({
        method: "health_sil.services.medicine_return_api.process_medicine_return",
        args: {
          pharmacy_billing_name: _billDoc.name,
          return_items: JSON.stringify(payload)
        },
        callback: function(r) {
          showSpinner(false);
          processBtn.disabled = false;
          if (r.message && r.message.ok) {
            showBanner(`✅ Return processed successfully! Stock Ledger Entries created.`, "success");
            printBtn.style.display = "inline-flex";
          } else {
            showBanner(`❌ Return failed: ${r.message?.errors?.join("; ") || "Unknown error"}`, "error");
          }
        },
        error: function() {
          showSpinner(false);
          processBtn.disabled = false;
          showBanner("❌ Server error during processing.", "error");
        }
      });
    });

    // --- Mode 2: By Patient Name Search ---
    const patientSearchBtn = $('#mr-patient-search-btn');
    const patientInput = $('#mr-patient-name');
    const patientResultsDiv = $('#mr-patient-results');
    const patientResultsList = $('#mr-patient-results-list');
    const patientResultsCount = $('#mr-patient-results-count');

    patientSearchBtn.addEventListener('click', searchByPatient);
    patientInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') searchByPatient(); });

    function searchByPatient() {
      const name = (patientInput.value || "").trim();
      if (!name) return;

      patientResultsDiv.style.display = 'none';
      showSpinner(true);

      frappe.call({
        method: "frappe.client.get_list",
        args: {
          doctype: "Pharmacy Billing",
          filters: { patient_name: ["like", `%${name}%`], docstatus: 1 },
          fields: ["name", "patient_name", "date_and_time", "rounded_total_amount"],
          order_by: "date_and_time desc",
          limit_page_length: 20
        },
        callback: function(r) {
          showSpinner(false);
          patientResultsList.innerHTML = "";
          const list = r.message || [];
          if (list.length === 0) {
            frappe.msgprint("No matching bills found.");
            return;
          }
          patientResultsCount.textContent = list.length;
          list.forEach(bill => {
            const row = document.createElement("div");
            row.style = "padding: 10px; border-bottom: 1px solid #eee; cursor: pointer; display: flex; justify-content: space-between;";
            row.innerHTML = `
              <div>
                <strong>${bill.name}</strong> - ${bill.patient_name}
                <div style="font-size: 11px; color: #666;">${bill.date_and_time}</div>
              </div>
              <strong style="color: #2b6cb0;">${fmt(bill.rounded_total_amount)}</strong>
            `;
            row.addEventListener('click', () => {
              billIdInput.value = bill.name;
              $('[data-mode="bill"]').click();
              fetchBill();
            });
            patientResultsList.appendChild(row);
          });
          patientResultsDiv.style.display = 'block';
        }
      });
    }

    // --- Mode 3: Walk-in (No Bill) Returns ---
    const wkBatch = $('#wk-batch');
    const wkItemName = $('#wk-item-name');
    const wkQty = $('#wk-qty');
    const wkMrp = $('#wk-mrp');
    const wkDisc = $('#wk-disc');
    const wkGst = $('#wk-gst');
    const wkHsn = $('#wk-hsn');
    const wkExpiry = $('#wk-expiry');
    const walkinAddBtn = $('#mr-walkin-add-btn');

    walkinAddBtn.addEventListener('click', () => {
      const batch = wkBatch.value.trim();
      const itemName = wkItemName.value.trim();
      const qty = flt(wkQty.value);
      const mrp = flt(wkMrp.value);
      const disc = flt(wkDisc.value);
      const gst = flt(wkGst.value);

      if (!batch || !itemName || qty <= 0 || mrp <= 0) {
        frappe.msgprint("Please fill Batch No, Medicine Name, Qty, and MRP.");
        return;
      }

      const gross = mrp * qty;
      const refund = gross - (gross * (disc / 100));

      _walkinItems.push({
        batch,
        item_name: itemName,
        qty,
        mrp,
        disc,
        gst,
        hsn: wkHsn.value.trim(),
        expiry: wkExpiry.value.trim(),
        refundAmt: refund
      });

      // Clear input fields
      wkBatch.value = "";
      wkItemName.value = "";
      wkQty.value = "1";
      wkMrp.value = "";
      wkDisc.value = "0";
      wkGst.value = "12";
      wkHsn.value = "";
      wkExpiry.value = "";

      renderWalkinTable();
    });

    function renderWalkinTable() {
      const walkinTbody = $('#mr-walkin-tbody');
      walkinTbody.innerHTML = "";

      _walkinItems.forEach((item, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${idx + 1}</td>
          <td>${item.hsn || "—"}</td>
          <td style="font-weight:600;">${item.item_name}</td>
          <td>${item.batch}</td>
          <td>${item.expiry || "—"}</td>
          <td>${item.qty}</td>
          <td>${fmt(item.mrp)}</td>
          <td>${item.disc}%</td>
          <td>${item.gst}%</td>
          <td style="text-align:right; font-weight:600; color:#e53e3e;">${fmt(item.refundAmt)}</td>
          <td><button class="mr-btn mr-btn-secondary" style="padding: 2px 6px; font-size: 11px;">❌</button></td>
        `;
        tr.querySelector('button').addEventListener('click', () => {
          _walkinItems.splice(idx, 1);
          renderWalkinTable();
        });
        walkinTbody.appendChild(tr);
      });

      const hasItems = _walkinItems.length > 0;
      $('#mr-walkin-table-wrap').style.display = hasItems ? 'block' : 'none';
      $('#mr-walkin-summary').style.display = hasItems ? 'flex' : 'none';
      $('#mr-walkin-action-bar').style.display = hasItems ? 'flex' : 'none';

      $('#wk-sum-items').textContent = _walkinItems.length;
      $('#wk-sum-qty').textContent = _walkinItems.reduce((s, i) => s + i.qty, 0);
      $('#wk-sum-total').textContent = fmt(_walkinItems.reduce((s, i) => s + i.refundAmt, 0));
      $('#mr-walkin-process-btn').disabled = !hasItems;
    }

    // Process Walk-in Return
    $('#mr-walkin-process-btn').addEventListener('click', function() {
      if (_walkinItems.length === 0) return;
      if (!confirm("Confirm walk-in return process? This will directly sync Batch Stock values.")) return;

      showSpinner(true);
      // Sequentially update Batch docs
      const promises = _walkinItems.map(item => {
        return new Promise((resolve) => {
          frappe.call({
            method: "frappe.client.get",
            args: { doctype: "Batch", name: item.batch },
            callback: function(r) {
              if (r.message) {
                const currentQty = flt(r.message.batch_qty);
                frappe.call({
                  method: "frappe.client.set_value",
                  args: {
                    doctype: "Batch",
                    name: item.batch,
                    fieldname: "batch_qty",
                    value: currentQty + item.qty
                  },
                  callback: resolve
                });
              } else {
                resolve();
              }
            }
          });
        });
      });

      Promise.all(promises).then(() => {
        showSpinner(false);
        frappe.msgprint("Walk-in Return processed and Batch quantities updated successfully.");
        _walkinItems = [];
        renderWalkinTable();
      });
    });

    $('#mr-walkin-clear-btn').addEventListener('click', () => {
      _walkinItems = [];
      renderWalkinTable();
    });

    // --- Print Return Bill (via Frappe print format "Pharmacy Return Bill") ---
    printBtn.addEventListener('click', function() {
      const selected = getSelectedItems();
      if (selected.length === 0) {
        showBanner("⚠️ No medicines selected. Please select items first.", "error");
        return;
      }

      const payload = selected.map(m => ({
        item_code: m.item_code,
        batch:     m.batch,
        qty:       m.retQty
      }));

      // /printview strips custom URL params before rendering Jinja, so we use
      // a server-side method that injects return_items into frappe.local.form_dict.
      frappe.call({
        method: 'health_sil.services.medicine_return_api.get_return_bill_html',
        args: {
          pharmacy_billing_name: _billDoc.name,
          return_items: JSON.stringify(payload)
        },
        callback: function(r) {
          if (!r.message) return;
          const win = window.open('', '_blank');
          win.document.open();
          win.document.write(r.message);
          win.document.close();
          win.focus();
          setTimeout(function() { win.print(); }, 800);
        }
      });
    });
  }
})();

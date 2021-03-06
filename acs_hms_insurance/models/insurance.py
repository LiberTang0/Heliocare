# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError, UserError, RedirectWarning, Warning


class InsuranceCompany(models.Model):
    _name = 'hms.insurance.company'
    _description = "Insurance Company"

    name = fields.Char('Name', required=True)
    description = fields.Text()


class Insurance(models.Model):
    _name = 'hms.patient.insurance'
    _description = "Patient Insurance"
    _rec_name = 'policy_number'
    
    patient_id = fields.Many2one('hms.patient', string ='Patient', ondelete='restrict', required=True)
    insurance_company_id = fields.Many2one('hms.insurance.company', string ="Insurance Company", required=True)
    policy_number = fields.Char(string ="Policy Number", required=True)
    insured_value = fields.Float(string ="Insured Value")
    validity = fields.Date(string="Validity")
    active = fields.Boolean(string="Active", default=True)
    note = fields.Text("Notes")


class InsuranceTPA(models.Model):
    _name = 'insurance.tpa'
    _description = "Insurance TPA"
    _inherits = {
        'res.partner': 'partner_id',
    }

    partner_id = fields.Many2one('res.partner', 'Partner', required=True, ondelete='restrict')


class InsuranceChecklistTemp(models.Model):
    _name = 'hms.insurance.checklist.template'
    _description = "Insurance Checklist Template"

    name = fields.Char('Name')
    active = fields.Boolean('Active', default=True)


class RequiredDocuments(models.Model):
    _name = 'hms.insurance.req.doc'
    _description = "Insurance Req Doc"
    
    name = fields.Char('Name')
    active = fields.Boolean('Active', default=True)


class InsuCheckList(models.Model):
    _name="hms.insurance.checklist"
    _description = "Insurance Checklist"

    name = fields.Char(string="Name")
    is_done = fields.Boolean(string="Y/N", default=False)
    remark = fields.Char(string="Remarks")
    claim_id = fields.Many2one("hms.insurance.claim", string="Claim")


class InsuranceClaim(models.Model):
    _name = 'hms.insurance.claim'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'acs.hms.mixin']
    _description = 'Claim'

    @api.depends('amount_requested', 'amount_pass')
    def _get_diff(self):
        for claim in self:
            claim.amount_difference = claim.amount_requested - claim.amount_pass

    @api.model
    def _default_insu_checklist(self):
        vals = []
        checklists = self.env['hms.insurance.checklist.template'].search([('active', '=', True)])
        for checklist in checklists:
            vals.append((0, 0, {
                'name': checklist.name,
            }))
        return vals

    @api.depends('checklist_ids')
    def _compute_checklist_ids_marked(self):
        for rec in self:
            done_checklist = rec.checklist_ids.filtered(lambda x: x.is_done)
            if len(rec.checklist_ids)>=1:
                rec.checklist_marked = (len(done_checklist)* 100)/len(rec.checklist_ids)

    STATES={'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    name = fields.Char('Claim Number', required=True, default="/", states=STATES)
    patient_id = fields.Many2one('hms.patient', 'Patient', required=True, states=STATES)
    insurance_id = fields.Many2one('hms.patient.insurance', 'Insurance Policy', required=True, states=STATES)
    hospitalization_id = fields.Many2one('acs.hospitalization', 'Hospitalization', required=True, states=STATES)
    insurance_company_id = fields.Many2one('hms.insurance.company', related="insurance_id.insurance_company_id", string='Insurance Company', readonly=True, store=True)
    amount_requested = fields.Float('Total Claim Amount', states=STATES)
    amount_pass = fields.Float('Passed Amount', states=STATES)
    amount_received = fields.Float('Received Amount', states=STATES)
    amount_difference = fields.Float(compute='_get_diff', string='Difference Amount', states=STATES)
    date = fields.Datetime(string='Claim Date', default=fields.Datetime.now, states=STATES)
    date_received = fields.Date('Claim Received Date', states=STATES)
    tpa_id = fields.Many2one('insurance.tpa', 'TPA', states=STATES)
    req_document_ids = fields.Many2many('hms.insurance.req.doc', 'hms_insurance_req_doc_rel', 'claim_id', 'doc_id', 'Required Documents', states=STATES)
    question = fields.Text('Question', states=STATES)
    answer = fields.Text('Answer', states=STATES)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('sent', 'Sent For Approval'),
        ('approve', 'Approved'),
        ('received', 'Received'),
        ('cancel', 'Canceled'),
        ('done', 'Done')], 'State', default='draft')
    doc_ids = fields.One2many(comodel_name='ir.attachment', inverse_name='claim_id', string='Document', states=STATES)
    checklist_ids = fields.One2many('hms.insurance.checklist', 'claim_id', string='Checklist', default=lambda self: self._default_insu_checklist(), states=STATES)
    package_id = fields.Many2one('hospitalization.package', related="hospitalization_id.package_id", string='Package', readonly=True)
    checklist_marked = fields.Float('Checklist Progress', compute='_compute_checklist_ids_marked',store=True, states=STATES)

    def unlink(self):
        for data in self:
            if data.state in ['done']:
                raise UserError(('You can not delete record in done state'))
        return super(InsuranceClaim, self).unlink()

    @api.onchange('package_id')
    def onchange_package_id(self):
        if self.package_id:
            self.amount_requested = self.package_id.amount_total

    def action_draft(self):
        self.state = 'draft'

    def action_confirm(self):
        if self.name=='/':
            self.name = self.env['ir.sequence'].next_by_code('hms.insurance.claim') or 'New Claim'
        self.state = 'confirm'

    def action_sent(self):
        self.state = 'sent'

    def action_approve(self):
        self.state = 'approve'

    def action_received(self):
        self.state = 'received'

    def action_done(self):
        self.date_received = fields.Date.today()
        self.state = 'done'

    def action_cancel(self):
        self.state = 'cancel'

    def action_view_invoice(self):
        invoices = self.env['account.move'].search([('claim_id', '=', self.id)])
        action = self.acs_action_view_invoice(invoices)
        return action

    def action_view_hospitalization_invoice(self):
        invoices = self.env['account.move'].search([('hospitalization_id', '=', self.hospitalization_id.id)])
        action = self.acs_action_view_invoice(invoices)
        return action

    def action_payments(self):
        action = self.env.ref('account.action_account_payments_payable').read()[0]
        action['domain'] = [('claim_id','=',self.id)]
        action['context'] = {
            'default_claim_id': self.id,
            'default_payment_type': 'inbound',
            'default_partner_id': self.patient_id.partner_id.id}
        return action

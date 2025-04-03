# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta
import base64
import io
import xlsxwriter

class AttendanceRealtimeWizard(models.TransientModel):
    _name = 'dityc.attendance.realtime.wizard'
    _description = 'Wizard para Reporte de Asistencias'

    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    fecha_desde = fields.Date(string='Fecha Desde', required=True, default=lambda self: fields.Date.today() - timedelta(days=30))
    fecha_hasta = fields.Date(string='Fecha Hasta', required=True, default=lambda self: fields.Date.today())
    employee_ids = fields.Many2many('hr.employee', string='Empleados', domain="[('company_id', '=', company_id)]")
    group_by_employee = fields.Boolean(string='Agrupar por Empleado', default=False)
    show_group_by_employee = fields.Boolean(compute='_compute_show_group_by_employee', store=False)
    show_details = fields.Boolean(string='Mostrar Detalles', default=True)
    group_by_date = fields.Boolean(string='Agrupar por Fecha', default=True)

    # Campos para el archivo Excel
    excel_file = fields.Binary('Archivo Excel')
    excel_filename = fields.Char('Nombre del archivo Excel')

    @api.depends('employee_ids')
    def _compute_show_group_by_employee(self):
        """Determina si se debe mostrar la opción de agrupar por empleado"""
        for wizard in self:
            wizard.show_group_by_employee = not wizard.employee_ids

    def action_view_attendance(self):
        """Abre la vista web del reporte de asistencias"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f'{base_url}/asistencia/reporte_web?wizard_id=%s' % self.id,
            'target': 'new'
        }

    def action_export_excel(self):
        """Exporta el reporte de asistencias a Excel"""
        self.ensure_one()

        # Crear el archivo Excel en memoria
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Reporte de Asistencias')

        # Estilos
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'fg_color': '#1e293b',
            'font_color': 'white',
            'border': 1
        })

        group_format = workbook.add_format({
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'fg_color': '#1e293b',
            'font_color': 'white',
            'border': 1
        })

        total_format = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'fg_color': '#f0f9ff',
            'font_color': '#0ea5e9',
            'border': 1,
            'num_format': '#,##0.00'
        })

        number_format = workbook.add_format({
            'align': 'right',
            'num_format': '#,##0.00'
        })

        date_format = workbook.add_format({
            'align': 'center',
            'num_format': 'dd/mm/yyyy'
        })

        time_format = workbook.add_format({
            'align': 'center',
            'num_format': 'hh:mm:ss'
        })

        # Encabezados
        headers = [
            'Empleado', 'Fecha', 'Día', 'Tipo', 'Entrada', 'Salida',
            'Hrs Normal', 'Hrs 50%', 'Hrs 100%', 'Hrs Feriado', 'Total Hrs'
        ]
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Ajustar anchos de columna
        worksheet.set_column('A:A', 30)  # Empleado
        worksheet.set_column('B:B', 12)  # Fecha
        worksheet.set_column('C:C', 12)  # Día
        worksheet.set_column('D:D', 15)  # Tipo
        worksheet.set_column('E:F', 10)  # Entrada/Salida
        worksheet.set_column('G:K', 12)  # Horas

        # Obtener datos
        domain = [
            ('fecha', '>=', self.fecha_desde),
            ('fecha', '<=', self.fecha_hasta),
        ]
        
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
            
        attendances = self.env['dityc.attendance.realtime.cache'].search(domain)
        
        # Escribir datos
        row = 1
        if self.group_by_employee and not self.employee_ids:
            # Agrupar por empleado
            employee_groups = {}
            for attendance in attendances:
                if attendance.employee_id not in employee_groups:
                    employee_groups[attendance.employee_id] = {
                        'entries': [],
                        'totals': {
                            'horas_semana_normal': 0,
                            'horas_sabado_50': 0,
                            'horas_extra_100': 0,
                            'horas_feriado': 0,
                            'total_horas_trabajadas': 0
                        }
                    }
                employee_groups[attendance.employee_id]['entries'].append(attendance)
                employee_groups[attendance.employee_id]['totals']['horas_semana_normal'] += attendance.horas_semana_normal or 0
                employee_groups[attendance.employee_id]['totals']['horas_sabado_50'] += attendance.horas_sabado_50 or 0
                employee_groups[attendance.employee_id]['totals']['horas_extra_100'] += attendance.horas_extra_100 or 0
                employee_groups[attendance.employee_id]['totals']['horas_feriado'] += attendance.horas_feriado or 0
                employee_groups[attendance.employee_id]['totals']['total_horas_trabajadas'] += attendance.total_horas_trabajadas or 0

            for employee, data in employee_groups.items():
                # Encabezado del grupo
                worksheet.merge_range(row, 0, row, 5, employee.name, group_format)
                worksheet.write(row, 6, data['totals']['horas_semana_normal'], total_format)
                worksheet.write(row, 7, data['totals']['horas_sabado_50'], total_format)
                worksheet.write(row, 8, data['totals']['horas_extra_100'], total_format)
                worksheet.write(row, 9, data['totals']['horas_feriado'], total_format)
                worksheet.write(row, 10, data['totals']['total_horas_trabajadas'], total_format)
                row += 1

                # Detalles
                for entry in data['entries']:
                    worksheet.write(row, 0, '')  # Empleado (vacío en detalles)
                    worksheet.write(row, 1, entry.fecha, date_format)
                    worksheet.write(row, 2, entry.dia_semana)
                    worksheet.write(row, 3, entry.tipo_dia)
                    worksheet.write(row, 4, entry.entrada, time_format)
                    worksheet.write(row, 5, entry.salida, time_format)
                    worksheet.write(row, 6, entry.horas_semana_normal or 0, number_format)
                    worksheet.write(row, 7, entry.horas_sabado_50 or 0, number_format)
                    worksheet.write(row, 8, entry.horas_extra_100 or 0, number_format)
                    worksheet.write(row, 9, entry.horas_feriado or 0, number_format)
                    worksheet.write(row, 10, entry.total_horas_trabajadas or 0, number_format)
                    row += 1
        else:
            # Sin agrupar
            for attendance in attendances:
                worksheet.write(row, 0, attendance.employee_id.name)
                worksheet.write(row, 1, attendance.fecha, date_format)
                worksheet.write(row, 2, attendance.dia_semana)
                worksheet.write(row, 3, attendance.tipo_dia)
                worksheet.write(row, 4, attendance.entrada, time_format)
                worksheet.write(row, 5, attendance.salida, time_format)
                worksheet.write(row, 6, attendance.horas_semana_normal or 0, number_format)
                worksheet.write(row, 7, attendance.horas_sabado_50 or 0, number_format)
                worksheet.write(row, 8, attendance.horas_extra_100 or 0, number_format)
                worksheet.write(row, 9, attendance.horas_feriado or 0, number_format)
                worksheet.write(row, 10, attendance.total_horas_trabajadas or 0, number_format)
                row += 1

        workbook.close()
        
        # Guardar el archivo
        excel_data = output.getvalue()
        filename = f'Reporte_Asistencias_{self.fecha_desde.strftime("%Y%m%d")}_{self.fecha_hasta.strftime("%Y%m%d")}.xlsx'
        
        self.write({
            'excel_file': base64.b64encode(excel_data),
            'excel_filename': filename
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=excel_file&download=true&filename={filename}',
            'target': 'self',
        } 
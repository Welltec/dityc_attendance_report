# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo import fields
from datetime import datetime, timedelta
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)

class DitycAttendanceReportController(http.Controller):

    def _group_attendances(self, attendances, wizard):
        """Agrupa las asistencias por empleado y calcula totales"""
        # Solo permitir agrupación si no hay empleados seleccionados
        if wizard.employee_ids or not wizard.group_by_employee:
            _logger.info("No aplicando agrupación: employee_ids=%s, group_by_employee=%s",
                       bool(wizard.employee_ids), wizard.group_by_employee)
            return attendances

        _logger.info("Aplicando agrupación por empleado para %s registros", len(attendances))
        
        grouped_data = []
        employee_groups = defaultdict(list)
        for att in attendances:
            employee_groups[att['employee_name']].append(att)
        
        _logger.info("Empleados agrupados: %s", list(employee_groups.keys()))
        
        for employee_name, atts in employee_groups.items():
            # Calcular totales para todas las columnas
            total_horas_normal = sum(float(a.get('horas_semana_normal') or 0) for a in atts)
            total_horas_sabado = sum(float(a.get('horas_sabado_50') or 0) for a in atts)
            total_horas_extra = sum(float(a.get('horas_extra_100') or 0) for a in atts)
            total_horas_feriado = sum(float(a.get('horas_feriado') or 0) for a in atts)
            total_horas = sum(float(a.get('total_horas_trabajadas') or 0) for a in atts)
            
            _logger.info("Totales para %s: Normal=%s, Sábado 50%%=%s, Extra=%s, Feriado=%s, Total=%s",
                        employee_name, total_horas_normal, total_horas_sabado, 
                        total_horas_extra, total_horas_feriado, total_horas)
            
            grouped_data.append({
                'is_group': True,
                'is_employee': True,
                'employee_name': employee_name,
                'horas_semana_normal': round(total_horas_normal, 2),
                'horas_sabado_50': round(total_horas_sabado, 2),
                'horas_extra_100': round(total_horas_extra, 2),
                'horas_feriado': round(total_horas_feriado, 2),
                'total_horas_trabajadas': round(total_horas, 2),
                'entries': atts
            })

        _logger.info("Agrupación completada: %s grupos generados", len(grouped_data))
        return grouped_data or attendances

    @http.route('/asistencia/reporte_web', type='http', auth='user', website=True)
    def attendance_report_web(self, wizard_id=None, **kw):
        """Controlador para mostrar el reporte web de asistencias"""
        if not wizard_id:
            return request.not_found()
        
        try:
            wizard_id = int(wizard_id)
            wizard = request.env['dityc.attendance.realtime.wizard'].browse(wizard_id)
            if not wizard.exists():
                return request.not_found()

            # Obtener datos del wizard
            domain = [
                ('fecha', '>=', wizard.fecha_desde),
                ('fecha', '<=', wizard.fecha_hasta),
            ]
            
            # Filtrar por empleados seleccionados
            if wizard.employee_ids:
                domain.append(('employee_id', 'in', wizard.employee_ids.ids))
            
            if wizard.company_id:
                domain.append(('company_id', '=', wizard.company_id.id))
                
            attendances = request.env['dityc.attendance.realtime.cache'].search(domain)
            
            # Obtener solo los empleados de la compañía actual
            employees_domain = [('company_id', '=', wizard.company_id.id)] if wizard.company_id else []
            employees = request.env['hr.employee'].search(employees_domain)
            
            # Preparar datos de asistencias con información del empleado
            attendance_data = []
            for attendance in attendances:
                attendance_data.append({
                    'id': attendance.id,
                    'employee_id': attendance.employee_id.id,
                    'employee_name': attendance.employee_id.name,
                    'fecha': attendance.fecha,
                    'dia_semana': attendance.dia_semana,
                    'entrada': attendance.entrada,
                    'salida': attendance.salida,
                    'tipo_dia': attendance.tipo_dia,
                    'es_feriado': attendance.es_feriado,
                    'nombre_feriado': attendance.nombre_feriado,
                    'es_dia_laborable': attendance.es_dia_laborable,
                    'horas_semana_normal': attendance.horas_semana_normal or 0.0,
                    'horas_sabado_50': attendance.horas_sabado_50 or 0.0,
                    'horas_extra_100': attendance.horas_extra_100 or 0.0,
                    'horas_feriado': attendance.horas_feriado or 0.0,
                    'total_horas_trabajadas': attendance.total_horas_trabajadas or 0.0
                })

            # Aplicar agrupación según la configuración del wizard
            grouped_data = self._group_attendances(attendance_data, wizard)
            
            if not grouped_data:
                error_message = 'No hay datos para mostrar en el período seleccionado.'
                return request.render('dityc_attendance_report.attendance_report_template', {
                    'error_message': error_message,
                    'wizard_id': wizard_id,
                    'employees': employees,
                    'employee_ids': wizard.employee_ids.ids,
                    'fecha_desde': wizard.fecha_desde,
                    'fecha_hasta': wizard.fecha_hasta,
                    'company_name': wizard.company_id.name,
                    'attendances': [],
                    'show_group_by_employee': not wizard.employee_ids,
                    'group_by_employee': wizard.group_by_employee and not wizard.employee_ids,
                    'filters': {
                        'employees': ', '.join(wizard.employee_ids.mapped('name')) if wizard.employee_ids else 'Todos',
                    },
                    'total_attendances': 0,
                    'total_horas_semana_normal': 0.0,
                    'total_horas_sabado_50': 0.0,
                    'total_horas_extra_100': 0.0,
                    'total_horas_feriado': 0.0,
                    'total_horas_trabajadas': 0.0
                })
            
            # Calcular totales generales para el pie de tabla
            # Hacemos esto antes de asignar grouped_data a values para tener los totales originales
            total_normal = 0.0
            total_sabado_50 = 0.0
            total_extra_100 = 0.0
            total_feriado = 0.0
            total_trabajadas = 0.0
            
            if attendance_data:
                # Agregar logging para depuración
                _logger.info("Calculando totales para %s registros de asistencia", len(attendance_data))
                
                for att in attendance_data:
                    # Convertir valores a float y asegurar que no sean None
                    horas_normal = float(att.get('horas_semana_normal') or 0)
                    horas_sabado = float(att.get('horas_sabado_50') or 0)
                    horas_extra = float(att.get('horas_extra_100') or 0)
                    horas_feriado = float(att.get('horas_feriado') or 0)
                    horas_total = float(att.get('total_horas_trabajadas') or 0)
                    
                    # Acumular totales
                    total_normal += horas_normal
                    total_sabado_50 += horas_sabado
                    total_extra_100 += horas_extra
                    total_feriado += horas_feriado
                    total_trabajadas += horas_total
                
                # Registrar valores para depuración
                _logger.info("Totales calculados: Normal: %s, Sábado 50%%: %s, Extra 100%%: %s, Feriado: %s, Total: %s",
                             total_normal, total_sabado_50, total_extra_100, total_feriado, total_trabajadas)
            else:
                _logger.warning("No hay datos de asistencia para calcular totales")
            
            # Preparar datos para la vista
            values = {
                'wizard_id': wizard_id,
                'company_name': wizard.company_id.name,
                'fecha_desde': wizard.fecha_desde,
                'fecha_hasta': wizard.fecha_hasta,
                'attendances': grouped_data,
                'employees': employees,
                'employee_ids': wizard.employee_ids.ids,
                'show_group_by_employee': not wizard.employee_ids,
                'group_by_employee': wizard.group_by_employee and not wizard.employee_ids,
                'filters': {
                    'employees': ', '.join(wizard.employee_ids.mapped('name')) if wizard.employee_ids else 'Todos',
                },
                'total_attendances': len(attendances),
                'error_message': False,
                'total_horas_semana_normal': round(total_normal, 2),
                'total_horas_sabado_50': round(total_sabado_50, 2),
                'total_horas_extra_100': round(total_extra_100, 2),
                'total_horas_feriado': round(total_feriado, 2),
                'total_horas_trabajadas': round(total_trabajadas, 2)
            }
            
            return request.render('dityc_attendance_report.attendance_report_template', values)
            
        except Exception as e:
            _logger.error("Error al generar la vista web del reporte de asistencias: %s", str(e))
            return request.render('dityc_attendance_report.attendance_report_template', {
                'error_message': 'Error al generar el reporte. Por favor, contacte al administrador.',
                'wizard_id': wizard_id,
                'employees': request.env['hr.employee'].search([]),
                'employee_ids': [],
                'fecha_desde': fields.Date.today() - timedelta(days=30),
                'fecha_hasta': fields.Date.today(),
                'company_name': request.env.company.name,
                'attendances': [],
                'show_group_by_employee': True,
                'group_by_employee': False,
                'filters': {
                    'employees': 'Todos'
                },
                'total_attendances': 0,
                'total_horas_semana_normal': 0.0,
                'total_horas_sabado_50': 0.0,
                'total_horas_extra_100': 0.0,
                'total_horas_feriado': 0.0,
                'total_horas_trabajadas': 0.0
            })

    @http.route(['/attendance/report/data'], type='json', auth='user')
    def get_attendance_data(self, fecha_desde=None, fecha_hasta=None, employee_ids=None, **kw):
        """Controlador para obtener datos de asistencias en formato JSON"""
        domain = []
        if fecha_desde:
            domain.append(('fecha', '>=', fecha_desde))
        if fecha_hasta:
            domain.append(('fecha', '<=', fecha_hasta))
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))

        attendances = request.env['dityc.attendance.realtime.cache'].search_read(
            domain=domain,
            fields=['employee_id', 'fecha', 'entrada', 'salida', 'total_horas_trabajadas']
        )
        return attendances 
# -*- coding: utf-8 -*-
{
    'name': 'DITyC Attendance Report',
    'version': '17.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Reporte avanzado de asistencias con cálculo de horas',
    'description': """
        Módulo de reportes de asistencia con:
        * Cálculo automático de horas normales, extras y feriados
        * Vista materializada para mejor rendimiento
        * Reportes en PDF y Excel
        * Análisis por empleado y período
        * Wizard para filtros avanzados
        * Vista web interactiva
    """,
    'author': 'DITyC',
    'website': 'https://www.dityc.com.ar',
    'depends': [
        'base',
        'hr',
        'hr_attendance',
        'hr_holidays',
        'resource',
        'web',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/attendance_realtime_views.xml',
        'views/attendance_realtime_wizard_views.xml',
        'views/attendance_report_template.xml',
        'views/menus.xml',
        'report/attendance_report.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
} 
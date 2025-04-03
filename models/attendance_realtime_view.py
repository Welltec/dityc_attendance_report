# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _
from odoo.fields import Datetime
from datetime import datetime, timedelta
import pytz
import json
from lxml import etree
import base64
import xlsxwriter
from io import BytesIO
import logging
from dateutil.relativedelta import relativedelta
from psycopg2.extensions import AsIs
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AttendanceRealtimeView(models.Model):
    _name = 'dityc.attendance.realtime.view'
    _description = 'Vista en Tiempo Real de Asistencias'
    _auto = False
    _order = 'fecha desc, employee_id, entrada'

    id = fields.Integer(string='ID', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    fecha = fields.Date(string='Fecha', readonly=True)
    dia_semana = fields.Char(string='Día', readonly=True)
    entrada = fields.Datetime(string='Entrada', readonly=True)
    salida = fields.Datetime(string='Salida', readonly=True)
    tipo_dia = fields.Selection([
        ('habil', 'Hábil'),
        ('sabado_am', 'Sáb AM'),
        ('sabado_pm', 'Sáb PM'),
        ('domingo', 'Dom'),
        ('feriado', 'Feriado'),
        ('no_laborable', 'No Lab.')
    ], string='Tipo', readonly=True)
    es_feriado = fields.Boolean(string='Feriado', readonly=True)
    nombre_feriado = fields.Char(string='Desc. Feriado', readonly=True)
    horas_semana_normal = fields.Float(string='Normal L-V', digits=(16, 2), readonly=True)
    horas_sabado_50 = fields.Float(string='50% Sáb', digits=(16, 2), readonly=True)
    horas_extra_100 = fields.Float(string='100% S/D', digits=(16, 2), readonly=True)
    horas_feriado = fields.Float(string='Hrs Feriado', digits=(16, 2), readonly=True)
    total_horas_trabajadas = fields.Float(string='Total Hrs', digits=(16, 2), readonly=True)

    @api.model
    def init(self):
        """Inicializa la vista materializada"""
        try:
            # Para una vista normal, simplemente la reemplazamos
            tools.drop_view_if_exists(self.env.cr, self._table)
            _logger.info("Vista %s eliminada, se creará desde cero", self._table)
              
            # Establecer la zona horaria para toda la sesión
            self.env.cr.execute("SET TIME ZONE 'America/Argentina/Buenos_Aires'")
            
            # Crear la vista
            self.env.cr.execute("""
                -- Crear vista con zona horaria America/Argentina/Buenos_Aires
                CREATE OR REPLACE VIEW dityc_attendance_realtime_view AS
                WITH 
                -- Constantes para definir los límites horarios
                constants AS (
                    SELECT 
                        '00:01:00'::time as inicio_sabado_50,
                        '13:00:00'::time as limite_sabado_50,
                        '13:01:00'::time as inicio_sabado_100
                ),
                date_series AS (
                    -- Generar fechas solo para los últimos 3 meses (mes actual y dos anteriores)
                    SELECT generate_series(
                        (date_trunc('month', NOW()) - interval '2 month')::date,
                        (date_trunc('month', NOW() + interval '1 month') - interval '1 day')::date,
                        '1 day'::interval
                    )::date AS fecha
                ),
                employees AS (
                    -- Obtener todos los empleados activos para los últimos 3 meses
                    SELECT id, company_id FROM hr_employee WHERE active = true
                ),
                employee_dates AS (
                    -- Generar una fila por cada empleado y fecha
                    SELECT 
                        e.id as employee_id,
                        e.company_id,
                        d.fecha,
                        CASE EXTRACT(DOW FROM d.fecha)
                            WHEN 0 THEN 'Domingo'
                            WHEN 1 THEN 'Lunes'
                            WHEN 2 THEN 'Martes'
                            WHEN 3 THEN 'Miércoles'
                            WHEN 4 THEN 'Jueves'
                            WHEN 5 THEN 'Viernes'
                            WHEN 6 THEN 'Sábado'
                        END as dia_semana,
                        EXTRACT(DOW FROM d.fecha) as dow
                    FROM employees e
                    CROSS JOIN date_series d
                ),
                holidays AS (
                    -- Obtener todos los feriados de los últimos 3 meses
                    -- Combinamos feriados individuales por empleado y feriados globales
                    SELECT 
                        l.employee_id,
                        l.request_date_from::date as fecha,
                        lt.name::text as nombre_feriado
                    FROM hr_leave l
                    JOIN hr_leave_type lt ON l.holiday_status_id = lt.id
                    WHERE lt.work_entry_type_id IN (SELECT id FROM hr_work_entry_type WHERE is_leave IS TRUE)
                    AND l.state = 'validate'
                    AND l.request_date_from::date >= (date_trunc('month', NOW()) - interval '2 month')::date
                    
                    UNION
                    
                    -- Feriados nacionales para todos los empleados
                    -- Incluimos feriados desde una tabla global de feriados o fechas específicas
                    SELECT 
                        e.id as employee_id,
                        date_holiday as fecha,
                        national_holidays.name::text as nombre_feriado
                    FROM hr_employee e
                    CROSS JOIN (
                        -- Lista de feriados nacionales que aplican a todos los empleados
                        -- Esta consulta se puede reemplazar por una tabla real de feriados si existe
                        SELECT '2025-04-02'::date as date_holiday, 'Día de los Veteranos y Caídos en Malvinas' as name
                        UNION ALL SELECT '2025-01-01'::date, 'Año Nuevo'
                        UNION ALL SELECT '2025-02-24'::date, 'Carnaval'
                        UNION ALL SELECT '2025-02-25'::date, 'Carnaval'
                        UNION ALL SELECT '2025-03-24'::date, 'Día de la Memoria'
                        UNION ALL SELECT '2025-04-18'::date, 'Viernes Santo'
                        UNION ALL SELECT '2025-05-01'::date, 'Día del Trabajador'
                        UNION ALL SELECT '2025-05-25'::date, 'Día de la Revolución de Mayo'
                        UNION ALL SELECT '2025-06-20'::date, 'Día de la Bandera'
                        UNION ALL SELECT '2025-07-09'::date, 'Día de la Independencia'
                        UNION ALL SELECT '2025-08-17'::date, 'Paso a la Inmortalidad del Gral. San Martín'
                        UNION ALL SELECT '2025-10-12'::date, 'Día del Respeto a la Diversidad Cultural'
                        UNION ALL SELECT '2025-11-20'::date, 'Día de la Soberanía Nacional'
                        UNION ALL SELECT '2025-12-08'::date, 'Inmaculada Concepción de María'
                        UNION ALL SELECT '2025-12-25'::date, 'Navidad'
                    ) AS national_holidays
                    WHERE date_holiday >= (date_trunc('month', NOW()) - interval '2 month')::date
                ),
                attendance_data AS (
                    -- Procesar las asistencias de los últimos 3 meses
                    SELECT 
                        a.id,
                        a.employee_id,
                        e.company_id,
                        -- Convertir check_in/check_out a zona horaria local
                        (a.check_in AT TIME ZONE 'UTC')::date as fecha,
                        (a.check_in AT TIME ZONE 'UTC') as entrada,
                        (a.check_out AT TIME ZONE 'UTC') as salida,
                        -- Calcular horas totales
                        EXTRACT(EPOCH FROM (
                            (a.check_out AT TIME ZONE 'UTC') - (a.check_in AT TIME ZONE 'UTC')
                        )) / 3600.0 as horas_totales
                    FROM hr_attendance a
                    JOIN hr_employee e ON e.id = a.employee_id
                    WHERE a.check_out IS NOT NULL
                    AND (a.check_in AT TIME ZONE 'UTC')::date >= (date_trunc('month', NOW()) - interval '2 month')::date
                )
                SELECT 
                    COALESCE(ad.id, -ed.employee_id) AS id,
                    ed.employee_id,
                    ed.company_id,
                    ed.fecha,
                    ed.dia_semana,
                    ad.entrada,
                    ad.salida,
                    -- Determinar tipo de día
                    CASE 
                        -- Primero verificar si es un feriado
                        WHEN EXISTS (
                            SELECT 1 FROM holidays h
                            WHERE h.employee_id = ed.employee_id
                            AND h.fecha = ed.fecha
                        ) THEN 'feriado'
                        -- Si no es feriado, determinar el tipo de día por día de la semana
                        WHEN ed.dow = 0 THEN 'domingo'
                        WHEN ed.dow = 6 THEN 
                            CASE 
                                -- Si no hay registro de entrada, usar valor por defecto
                                WHEN ad.entrada IS NULL THEN 'sabado_am'
                                -- Clasificar como sabado_am cuando la salida es antes o igual a las 13:00
                                WHEN (ad.salida AT TIME ZONE 'America/Argentina/Buenos_Aires')::time <= 
                                    (SELECT limite_sabado_50 FROM constants)
                                THEN 'sabado_am'
                                -- En cualquier otro caso (salida después de 13:00) es sabado_pm
                                ELSE 'sabado_pm'
                            END
                        ELSE 'habil'
                    END as tipo_dia,
                    -- Determinar si es feriado
                    EXISTS (
                        SELECT 1 FROM holidays h
                        WHERE h.employee_id = ed.employee_id
                        AND h.fecha = ed.fecha
                    ) as es_feriado,
                    -- Nombre del feriado
                    COALESCE((
                        SELECT h.nombre_feriado::text FROM holidays h
                        WHERE h.employee_id = ed.employee_id
                        AND h.fecha = ed.fecha
                        LIMIT 1
                    ), '') as nombre_feriado,
                    -- Horas normales (Lunes a Viernes todo el día)
                    CASE 
                        -- Solo calcular horas normales de lunes a viernes - nunca en sábados o domingos
                        WHEN ed.dow BETWEEN 1 AND 5 
                        -- No calcular horas normales si es feriado
                        AND NOT EXISTS (
                            SELECT 1 FROM holidays h
                            WHERE h.employee_id = ed.employee_id
                            AND h.fecha = ed.fecha
                        )
                        AND ad.id IS NOT NULL
                        THEN ROUND(ABS(ad.horas_totales), 2)
                        ELSE 0
                    END as horas_semana_normal,
                    -- Horas sábado 50% (00:01 a 13:00)
                    CASE 
                        -- Solo calcular horas 50% en sábados, nunca en domingos
                        WHEN ed.dow = 6 
                        -- No calcular horas 50% si es feriado
                        AND NOT EXISTS (
                            SELECT 1 FROM holidays h
                            WHERE h.employee_id = ed.employee_id
                            AND h.fecha = ed.fecha
                        )
                        AND ad.id IS NOT NULL
                        THEN 
                            CASE
                                -- REGLA 1: Si salida es antes o igual a las 13:00, todas las horas son 50%
                                WHEN (ad.salida AT TIME ZONE 'America/Argentina/Buenos_Aires')::time <= (SELECT limite_sabado_50 FROM constants)
                                THEN ROUND(ABS(ad.horas_totales), 2)
                                
                                -- REGLA 3 PARTE 1: Si entrada antes de 13:00 y salida después, calcular solo horas hasta 13:00
                                WHEN (ad.entrada AT TIME ZONE 'America/Argentina/Buenos_Aires')::time < (SELECT limite_sabado_50 FROM constants)
                                AND (ad.salida AT TIME ZONE 'America/Argentina/Buenos_Aires')::time > (SELECT limite_sabado_50 FROM constants)
                                THEN ROUND(
                                    ABS(EXTRACT(EPOCH FROM (
                                        (ed.fecha + (SELECT limite_sabado_50 FROM constants))::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires'
                                        - ad.entrada AT TIME ZONE 'America/Argentina/Buenos_Aires'
                                    )) / 3600.0),
                                    2)
                                
                                -- REGLA 2: Si entrada es después de las 13:00, no hay horas al 50%
                                ELSE 0
                            END
                        ELSE 0
                    END as horas_sabado_50,
                    -- Horas 100% (sábado 13:01 hasta domingo 23:59)
                    CASE 
                        WHEN (
                            -- Sábado o domingo
                            ((ed.dow = 6 OR ed.dow = 0) AND ad.id IS NOT NULL)
                        )
                        -- No calcular horas 100% si es feriado
                        AND NOT EXISTS (
                            SELECT 1 FROM holidays h
                            WHERE h.employee_id = ed.employee_id
                            AND h.fecha = ed.fecha
                        )
                        THEN 
                            CASE
                                -- REGLA: Para domingos, todas las horas son 100%
                                WHEN ed.dow = 0
                                THEN ROUND(ABS(ad.horas_totales), 2)
                                
                                -- REGLA 2: Para sábados, si la entrada es a partir de las 13:00, todas las horas son 100%
                                WHEN ed.dow = 6 AND (ad.entrada AT TIME ZONE 'America/Argentina/Buenos_Aires')::time >= (SELECT limite_sabado_50 FROM constants)
                                THEN ROUND(ABS(ad.horas_totales), 2)
                                
                                -- REGLA 3 PARTE 2: Para sábados, si entrada antes de 13:00 y salida después, solo contar horas después de 13:00
                                WHEN ed.dow = 6 
                                    AND (ad.entrada AT TIME ZONE 'America/Argentina/Buenos_Aires')::time < (SELECT limite_sabado_50 FROM constants)
                                    AND (ad.salida AT TIME ZONE 'America/Argentina/Buenos_Aires')::time > (SELECT limite_sabado_50 FROM constants)
                                THEN ROUND(
                                    ABS(EXTRACT(EPOCH FROM (
                                        ad.salida AT TIME ZONE 'America/Argentina/Buenos_Aires'
                                        - (ed.fecha + (SELECT limite_sabado_50 FROM constants))::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires'
                                    )) / 3600.0),
                                    2)
                                
                                -- REGLA 1: Para sábados con salida antes o igual a las 13:00, no hay horas al 100%
                                ELSE 0
                            END
                        ELSE 0
                    END as horas_extra_100,
                    -- Horas feriado (todo el día)
                    CASE 
                        -- Si es feriado, contar todas las horas como horas de feriado
                        WHEN EXISTS (
                            SELECT 1 FROM holidays h
                            WHERE h.employee_id = ed.employee_id
                            AND h.fecha = ed.fecha
                        )
                        AND ad.id IS NOT NULL
                        THEN ROUND(
                            ABS(ad.horas_totales),
                            2)
                        ELSE 0
                    END as horas_feriado,
                    -- Total horas trabajadas (suma de todas las categorías)
                    CASE 
                        WHEN ad.id IS NOT NULL
                        THEN ROUND(
                            ABS(ad.horas_totales),
                            2)
                        ELSE 0
                    END as total_horas_trabajadas
                FROM employee_dates ed
                LEFT JOIN attendance_data ad ON ed.employee_id = ad.employee_id AND ed.fecha = ad.fecha
                ORDER BY ed.fecha DESC, ed.employee_id
            """)
            _logger.info("Vista %s creada exitosamente", self._table)
            
            # Asegurarse de que el caché se actualiza
            self._notificar_cambios_cache()
            
        except Exception as e:
            _logger.error("Error al inicializar la vista materializada: %s", str(e))
            raise

    @api.model
    def _notificar_cambios_cache(self):
        """Notifica al caché que la vista se ha actualizado"""
        try:
            # Llamar al método de actualización automática del caché
            result = self.env['dityc.attendance.realtime.cache']._actualizar_cache_automatico()
            if result:
                _logger.info("Notificación de cambios enviada al caché y procesada correctamente")
            else:
                _logger.warning("No se pudo actualizar el caché, posiblemente porque la vista aún no está lista")
        except Exception as e:
            _logger.error(f"Error al notificar cambios al caché: {str(e)}")
            # No propagar el error para evitar que falle la inicialización de la vista

    @api.model
    def _actualizar_vista(self):
        """Actualiza la vista materializada"""
        try:
            _logger.info("Actualizando vista materializada")
            self.init()
            _logger.info("Vista materializada actualizada exitosamente")
        except Exception as e:
            _logger.error("Error al actualizar la vista materializada: %s", str(e))
            raise

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Sobrescribe fields_view_get para agregar campos dinámicos a la vista"""
        result = super(AttendanceRealtimeView, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        
        if view_type == 'tree':
            try:
                # Obtener el elemento tree
                doc = etree.XML(result['arch'])
                nodes = doc.xpath("//tree")
                if not nodes:
                    return result
                    
                tree = nodes[0]
                
                # Agregar total_horas_trabajadas al final
                total_horas = etree.Element('field', {
                    'name': 'total_horas_trabajadas',
                    'widget': 'float_time',
                    'sum': 'Total'
                })
                tree.append(total_horas)
                
                result['arch'] = etree.tostring(doc, encoding='unicode')
                _logger.info(f"Vista modificada exitosamente: {result['arch']}")
            except Exception as e:
                _logger.error(f"Error modificando la vista: {str(e)}")
        
        return result

    def export_xlsx(self):
        """Exporta los datos a Excel"""
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/export/xlsx_attendance_report',
            'target': 'self',
        }

    def refresh_view(self):
        """Actualiza la vista desde la interfaz de usuario"""
        try:
            self.env.cr.execute("SET TIME ZONE 'America/Argentina/Buenos_Aires'")
            self.init()
            # Actualizar los datos en el caché
            self._notificar_cambios_cache()
            # Para refrescar la vista en la interfaz
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        except Exception as e:
            _logger.error("Error al actualizar la vista: %s", str(e))
            raise UserError(_("Error al actualizar la vista: %s") % str(e)) 
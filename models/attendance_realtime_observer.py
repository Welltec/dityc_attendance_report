# -*- coding: utf-8 -*-

from odoo import models, api, fields
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    @api.model_create_multi
    def create(self, vals_list):
        """Sobrescribe create para actualizar la vista en tiempo real"""
        records = super(HrAttendance, self).create(vals_list)
        try:
            # Asegurar que las fechas estén truncadas a minutos
            for record in records:
                if record.check_in:
                    record.check_in = record.check_in.replace(second=0, microsecond=0)
                if record.check_out:
                    record.check_out = record.check_out.replace(second=0, microsecond=0)
            
            self.env['dityc.attendance.realtime.view']._actualizar_vista()
            _logger.info("Vista actualizada después de crear asistencias")
        except Exception as e:
            _logger.error("Error al actualizar vista después de crear asistencias: %s", str(e))
        return records

    def write(self, vals):
        """Sobrescribe el método write para actualizar el caché cuando se modifica un registro"""
        # Si se está modificando check_in o check_out, redondeamos los segundos
        if 'check_in' in vals and vals['check_in']:
            if isinstance(vals['check_in'], str):
                vals['check_in'] = fields.Datetime.from_string(vals['check_in'])
            vals['check_in'] = vals['check_in'].replace(second=0, microsecond=0)
            
        if 'check_out' in vals and vals['check_out']:
            if isinstance(vals['check_out'], str):
                vals['check_out'] = fields.Datetime.from_string(vals['check_out'])
            vals['check_out'] = vals['check_out'].replace(second=0, microsecond=0)
            
        # Llamar al método original
        res = super().write(vals)
        
        # Actualizar el caché
        self.env['dityc.attendance.realtime.cache']._actualizar_cache_automatico()
        
        return res

    def unlink(self):
        """Sobrescribe unlink para actualizar la vista en tiempo real"""
        result = super(HrAttendance, self).unlink()
        try:
            self.env['dityc.attendance.realtime.view']._actualizar_vista()
            _logger.info("Vista actualizada después de eliminar asistencias")
        except Exception as e:
            _logger.error("Error al actualizar vista después de eliminar asistencias: %s", str(e))
        return result 